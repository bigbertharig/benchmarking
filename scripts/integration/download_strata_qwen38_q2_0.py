#!/usr/bin/env python3
"""Stage the pinned Qwen3.8 Q2_0 pack on rig NVMe without using a GPU."""
from __future__ import annotations

import hashlib
import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

REVISION = "ed59f92082b1e93c0e96d60a8b11aab089b52f09"
REPO = "ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF"
TARGET = Path("/data/model-hotset/qwen3.8-flash-next-q2_0")
RECEIPT = TARGET / "download_terminal.json"
FILES = (
    ("Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00001-of-00002.gguf", 37623740192,
     "69820c02ec7d0b45ef2ebb19d6620299db749fe2aded7f39f93c6b88b199b720"),
    ("Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00002-of-00002.gguf", 28800138432,
     "316b46f3a2dbd68c900f43136ab9449f9dcc3725dfd8c794847c204bc161e113"),
)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write(state: dict, receipt: Path = RECEIPT) -> None:
    temporary = receipt.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, receipt)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shard", type=int, choices=(1, 2),
                    help="download and verify one shard in a separate manager job")
    args = ap.parse_args()
    files = FILES if args.shard is None else (FILES[args.shard - 1],)
    receipt_path = RECEIPT if args.shard is None else TARGET / f"shard_{args.shard}_terminal.json"
    TARGET.mkdir(parents=True, exist_ok=True)
    state = {"started_at": stamp(), "status": "running", "repo": REPO,
             "revision": REVISION, "target": str(TARGET), "files": [], "shard": args.shard}
    write(state, receipt_path)
    remaining = sum(max(0, size - min(size, (TARGET / f"{name}.part").stat().st_size
                                      if (TARGET / f"{name}.part").is_file() else 0))
                    for name, size, _ in files if not (TARGET / name).is_file())
    free = shutil.disk_usage(TARGET).free
    if free < remaining + 12 * 1024**3:
        state.update(status="failed", error=f"insufficient NVMe free space: {free} bytes",
                     finished_at=stamp())
        write(state, receipt_path)
        return 1
    try:
        for name, size, expected_hash in files:
            target = TARGET / name
            partial = TARGET / f"{name}.part"
            row = {"name": name, "size_bytes": size, "sha256_expected": expected_hash,
                   "started_at": stamp(), "status": "running"}
            state["files"].append(row)
            write(state, receipt_path)
            if args.shard is None and name == FILES[1][0]:
                sidecar = TARGET / "shard_2_terminal.json"
                deadline = time.monotonic() + 3 * 3600
                while sidecar.is_file():
                    status = json.loads(sidecar.read_text(encoding="utf-8")).get("status")
                    if status == "passed":
                        break
                    if status != "running":
                        raise RuntimeError(f"parallel shard 2 ended with {status}")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("parallel shard 2 did not finish within three hours")
                    time.sleep(60)
            if target.is_file() and target.stat().st_size == size and digest(target) == expected_hash:
                row["status"] = "verified_existing"
            else:
                url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/Q2_0/{name}"
                log = TARGET / f"{name}.curl.log"
                with log.open("ab") as output:
                    result = subprocess.run(["curl", "--fail", "--location", "--continue-at", "-",
                                             "--retry", "8", "--retry-delay", "10",
                                             "--connect-timeout", "30", "--output", str(partial), url],
                                            stdout=output, stderr=output)
                row["curl_exit"] = result.returncode
                if result.returncode:
                    raise RuntimeError(f"curl exited {result.returncode} for {name}")
                if partial.stat().st_size != size:
                    raise RuntimeError(f"size mismatch for {name}: {partial.stat().st_size} != {size}")
                actual_hash = digest(partial)
                row["sha256_actual"] = actual_hash
                if actual_hash != expected_hash:
                    raise RuntimeError(f"SHA-256 mismatch for {name}")
                os.replace(partial, target)
                row["status"] = "downloaded_verified"
            row["finished_at"] = stamp()
            write(state, receipt_path)
        state["status"] = "passed"
    except Exception as exc:
        state.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    state["finished_at"] = stamp()
    write(state, receipt_path)
    print(f"Qwen3.8 download {state['status']}: {state.get('error', '')}", flush=True)
    return 0 if state["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
