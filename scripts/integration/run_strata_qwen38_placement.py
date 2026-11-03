#!/usr/bin/env python3
"""Probe Qwen3.8 Strata expert placement on leased GPU 0, RAM and NVMe."""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import string
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CONTROL = Path("/data/bench-staging/strata-v0.2.10/control/bin/strata")
COMPONENTS = "/data/bench-staging/strata-v0.2.10/components"
DATA = "/data/bench-staging/strata-v0.2.10/data"
MODEL = Path("/data/model-hotset/qwen3.8-flash-next-q2_0")
RECEIPT = MODEL / "download_terminal.json"
PORT = 18131
BLOCK_DEVICES = {"nvme": Path("/sys/block/nvme0n1/stat"),
                 "sata_ssd": Path("/sys/block/sda/stat")}
PROMPT = ("Explain how a B-tree index serves searches, inserts, and deletes in a database. "
          "Include what happens during node splits and merges. " * 55)
FILLER = ("Section {n}. The rig log records routine status for each card: fan speed, temperature, power draw "
          "and memory in use. Nothing in this section changes the task. Entries repeat with new numbers, "
          "such as reading {n} at {m} watts and {k} degrees, to make the document long. ")
QUESTION_TOKENS = 256
DECODE_TOKENS = 160


def tokenizer(data_dir: Path):
    """Load the pack tokenizer exactly as Strata's server does."""
    root = Path("/data/bench-staging/strata-v0.2.10/control")
    sys.path.insert(0, str(root / "tools"))
    import strata_tokenizer as st
    path = data_dir / "packs/q2_0/tokenizer"
    vocab = json.loads((path / "vocab.json").read_text(encoding="utf-8"))
    tokens = [None] * len(vocab)
    for token, index in vocab.items():
        tokens[index] = token
    merges = (path / "merges.txt").read_text(encoding="utf-8").split("\n")
    types = json.loads((path / "token_type.json").read_text(encoding="utf-8"))
    config = json.loads((path / "tokenizer.json").read_text(encoding="utf-8"))
    return st.Tokenizer(tokens, merges, types, config.get("pre") or "qwen35",
                        config.get("special_ids") or None)


def depth_prompt(tok, context: int, fraction: float) -> tuple[str, str, int]:
    """Same marker and filler construction as capacity_run.depth_probe."""
    code = "".join(random.choice(string.ascii_uppercase) for _ in range(4)) + str(random.randint(1000, 9999))
    head = f"Remember this code: {code}. You will be asked for it at the end.\n\n"
    question = "\n\nWhat is the code given at the very start of this document? Reply with only the code."
    chunk = FILLER.format(n=1, m=100, k=50)
    chunk_tokens = len(tok.encode(chunk))
    head_tokens = len(tok.encode(head + question))
    target = int(context * fraction) - QUESTION_TOKENS
    count = max(1, (target - head_tokens) // max(1, chunk_tokens))
    body = "".join(FILLER.format(n=i, m=100 + i % 200, k=40 + i % 40) for i in range(count))
    prompt = head + body + question
    return prompt, code, len(tok.encode(prompt))


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(path: Path, state: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def gpu_mib() -> dict[str, int]:
    result = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used",
                             "--format=csv,noheader,nounits"], capture_output=True,
                            text=True, check=True)
    return {row.split(",")[0].strip(): int(row.split(",")[1].strip())
            for row in result.stdout.splitlines() if "," in row}


def memory() -> dict[str, int]:
    wanted = {"MemAvailable", "SwapFree", "SwapTotal", "Cached"}
    result = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in wanted:
            result[key + "_kib"] = int(value.split()[0])
    return result


def block_bytes() -> dict[str, dict[str, int]]:
    result = {}
    for name, path in BLOCK_DEVICES.items():
        parts = [int(value) for value in path.read_text().split()]
        result[name] = {"read_bytes": parts[2] * 512,
                        "written_bytes": parts[6] * 512}
    return result


def engine_io() -> dict[str, int | str] | None:
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            if "strata --serve" not in command or "qwen3.8" not in command.lower():
                continue
            values = {}
            for line in (entry / "io").read_text().splitlines():
                key, _, value = line.partition(":")
                if key in {"read_bytes", "write_bytes", "rchar", "wchar"}:
                    values[key] = int(value)
            values["pid"] = int(entry.name)
            values["command"] = command[:300]
            for line in (entry / "status").read_text().splitlines():
                key, _, value = line.partition(":")
                if key in {"VmRSS", "VmHWM", "VmSwap"}:
                    values[key + "_kib"] = int(value.split()[0])
            return values
        except (OSError, ValueError):
            continue
    return None


def request(path: str, body: dict | None = None, timeout: int = 10) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--data-dir", type=Path, default=Path(DATA),
                    help="Prepared Strata data directory; use a copy on SATA SSD for tier comparison")
    ap.add_argument("--evict-expert-cache", action="store_true",
                    help="Ask Linux to drop cached expert-file pages before launch")
    ap.add_argument("--resident-budget-gib", type=float,
                    help="GiB of experts copied into RAM; omit for Strata default")
    ap.add_argument("--gpus", default="0", help="Comma-separated physical GPU indices")
    ap.add_argument("--context", type=int, default=8192)
    ap.add_argument("--kv", choices=("int8", "q4_0", "k8v4", "fp16"), default="int8")
    ap.add_argument("--load-only", action="store_true", help="Validate placement without inference")
    ap.add_argument("--word-repetitions", type=int, default=0,
                    help="Send this many repeated words to exercise an actual long context")
    ap.add_argument("--depth-fractions", help="Run capacity_run style 10%/90% marker recall, e.g. 0.1,0.9")
    args = ap.parse_args()
    selected = [part.strip() for part in args.gpus.split(",")]
    if not selected or any(not part.isdigit() for part in selected):
        ap.error("--gpus must be comma-separated GPU indices")
    args.output.mkdir(parents=True, exist_ok=True)
    state = {"started_at": stamp(), "status": "running", "model": str(MODEL),
             "gpus": selected, "context": args.context, "kv": args.kv,
             "parallel": 1, "drafting": "off",
             "mtp": "off", "resident_budget_gib": args.resident_budget_gib,
             "word_repetitions": args.word_repetitions,
             "depth_fractions": args.depth_fractions,
             "data_dir": str(args.data_dir), "evict_expert_cache": args.evict_expert_cache,
             "block_counters": {name: str(path) for name, path in BLOCK_DEVICES.items()},
             "block_counter_scope": "host-wide"}
    save(args.output / "checkpoint.json", state)
    env = dict(os.environ, STRATA_COMPONENTS_DIR=COMPONENTS,
               CUDA_DEVICE_ORDER="PCI_BUS_ID")
    base = [str(CONTROL), "launch"]
    launch = base + ["--family", "qwen", "--model", "q2_0", "--model-path", str(MODEL),
                     "--data-dir", str(args.data_dir),
                     "--gpu", args.gpus, "--backend", "nvidia", "--vision", "off",
                     "--context", str(args.context), "--kv", args.kv,
                     "--parallel", "1", "--drafting", "off",
                     "--mtp", "off", "--port", str(PORT), "--access", "local",
                     "--no-api-key", "--tune", "skip", "--no-tui", "--yes", "--output", "json"]
    if args.resident_budget_gib is not None:
        launch += ["--set", f"resident-budget-gib={args.resident_budget_gib:g}"]
    state["launch_args"] = launch[2:]
    launched = False
    try:
        receipt = json.loads(RECEIPT.read_text())
        if receipt.get("status") != "passed":
            raise RuntimeError("model download receipt is not passed")
        expert_file = args.data_dir / "packs/q2_0/experts.bin"
        if not expert_file.is_file():
            raise FileNotFoundError(expert_file)
        state["expert_file"] = str(expert_file.resolve())
        state["expert_size_bytes"] = expert_file.stat().st_size
        state["expert_device_id"] = expert_file.stat().st_dev
        idle = gpu_mib()
        if any(idle[part] > 1024 for part in selected):
            raise RuntimeError("selected GPU is already in use")
        state["gpu_idle_mib"] = idle
        state["host_before"] = memory()
        state["block_before"] = block_bytes()
        if args.evict_expert_cache:
            with expert_file.open("rb") as stream:
                os.posix_fadvise(stream.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
            state["expert_cache_evict_at"] = stamp()
        t0 = time.monotonic()
        launched = True
        proc = subprocess.run(launch, env=env, capture_output=True, text=True, timeout=900)
        (args.output / "launch_stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (args.output / "launch_stderr.txt").write_text(proc.stderr, encoding="utf-8")
        state["launch_exit"] = proc.returncode
        state["launch_seconds"] = round(time.monotonic() - t0, 2)
        if proc.returncode:
            raise RuntimeError(f"Strata launch exited {proc.returncode}")
        for _ in range(30):
            try:
                state["health"] = request("/health", timeout=2)
                break
            except (OSError, ValueError):
                time.sleep(2)
        else:
            raise RuntimeError("Strata API did not become ready")
        state["gpu_loaded_mib"] = gpu_mib()
        state["host_loaded"] = memory()
        state["block_loaded"] = block_bytes()
        state["engine_io_loaded"] = engine_io()
        if state["host_loaded"]["MemAvailable_kib"] < 5 * 1024 * 1024:
            raise RuntimeError("less than 5 GiB MemAvailable after launch")
        state["requests"] = []
        fractions = ([float(value) for value in args.depth_fractions.split(",")]
                     if args.depth_fractions else [])
        if any(not 0 < value < 1 for value in fractions):
            raise ValueError("depth fractions must be between 0 and 1")
        tok = tokenizer(args.data_dir) if fractions else None
        trials = (() if args.load_only else
                  tuple((i + 1, DECODE_TOKENS) for i in range(len(fractions))) if fractions else
                  ((1, 64),) if args.word_repetitions else ((1, 128), (2, 128), (3, 512)))
        prompt = ((" the" * args.word_repetitions) +
                  "\nThe final answer is ORCHID. Reply with that word only."
                  if args.word_repetitions else PROMPT)
        state["prompt_characters"] = len(prompt)
        for repeat, limit in trials:
            code = None
            prompt_tokens_exact = None
            if fractions:
                prompt, code, prompt_tokens_exact = depth_prompt(tok, args.context, fractions[repeat - 1])
            disk_before = block_bytes()
            io_before = engine_io()
            t1 = time.monotonic()
            response = request("/v1/chat/completions", {"model": "strata", "messages": [
                {"role": "user", "content": prompt}], "max_tokens": limit,
                "temperature": 0}, timeout=1800)
            wall = round(time.monotonic() - t1, 3)
            save(args.output / f"response_{repeat}.json", response)
            message = (response.get("choices") or [{}])[0].get("message") or {}
            answer = (message.get("content") or "").strip()
            reasoning = (message.get("reasoning_content") or "").strip()
            final_answer = (answer.rsplit("</think>", 1)[-1].strip() if "</think>" in answer
                            else "" if "<think>" in answer else answer)
            state["requests"].append({"repeat": repeat, "max_tokens": limit,
                                      "target_fraction": fractions[repeat - 1] if fractions else None,
                                      "prompt_tokens_exact": prompt_tokens_exact,
                                      "prompt_characters": len(prompt),
                                      "recall_code": code,
                                      "answer": answer[:80], "answer_tail": answer[-160:],
                                      "final_answer": final_answer[:160],
                                      "recall_ok": code in (answer + reasoning) if code else None,
                                      "final_recall_ok": code in final_answer if code else None,
                                      "wall_seconds": wall,
                                      "usage": response.get("usage"),
                                      "finish_reason": (response.get("choices") or [{}])[0].get("finish_reason"),
                                      "gpu_mib": gpu_mib(), "host": memory(),
                                      "block_before": disk_before, "block_after": block_bytes(),
                                      "engine_io_before": io_before, "engine_io_after": engine_io()})
            save(args.output / "checkpoint.json", state)
        state["status"] = "passed"
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if launched:
            try:
                stopped = subprocess.run(base + ["--stop", "--output", "json"], env=env,
                                         capture_output=True, text=True, timeout=120)
                (args.output / "stop_stdout.txt").write_text(stopped.stdout, encoding="utf-8")
                (args.output / "stop_stderr.txt").write_text(stopped.stderr, encoding="utf-8")
                state["stop_exit"] = stopped.returncode
            except Exception as exc:
                state["stop_error"] = f"{type(exc).__name__}: {exc}"
        log_root = Path("/home/bryan/.local/state/strata")
        for folder, name in (("launch", "engine.log"), ("runtime", "server.log")):
            logs = sorted((log_root / folder).glob(f"*q2_0-{args.context // 1024}k*.log"),
                          key=lambda path: path.stat().st_mtime, reverse=True)
            if logs:
                shutil.copy2(logs[0], args.output / name)
        state["gpu_after_mib"] = gpu_mib()
        state["host_after"] = memory()
        state["block_after"] = block_bytes()
        state["finished_at"] = stamp()
        save(args.output / "terminal.json", state)
        message = f"Strata Qwen3.8 probe: {state['status']}"
        if state.get("error"):
            message += f" {state['error']}"
        print(message, flush=True)
    return 0 if state["status"] == "passed" and state.get("stop_exit") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
