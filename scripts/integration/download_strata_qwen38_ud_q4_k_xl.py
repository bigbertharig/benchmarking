#!/usr/bin/env python3
"""Stage the pinned Qwen3.8 UD-Q4_K_XL GGUF on the 4 TB shared drive."""
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

REVISION = "38bb39ee97821de2c9009abb7e93950eec396e66"
REPO = "unsloth/Qwen3.8-Flash-Next-GGUF"
TARGET = Path("/mnt/shared/models/qwen3.8-flash-next-ud-q4_k_xl")
RECEIPT = TARGET / "download_terminal.json"
FILES = (
    ("Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf", 10946624,
     "4448186216b3af4cc558bbce2c3213f01608f8f8b2e5267a9767971dd3ec8082"),
    ("Qwen3.8-Flash-Next-UD-Q4_K_XL-00002-of-00004.gguf", 49859583136,
     "3f342f1c1580473f1ee94ddd5b28206e8c07a70fa1a366f59d1d6c922919a6c9"),
    ("Qwen3.8-Flash-Next-UD-Q4_K_XL-00003-of-00004.gguf", 49376141504,
     "56758f40269cad5cd9b0d3d6fbae0f40f6d5be6de49e4ab392dbe83157d9cbd3"),
    ("Qwen3.8-Flash-Next-UD-Q4_K_XL-00004-of-00004.gguf", 12087983520,
     "753bda48b98ba4f1636134a90a967de1b2d3908a236c026e464777342e53510a"),
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
    ap.add_argument("--shard", type=int, choices=(1, 2, 3, 4),
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
        state.update(status="failed", error=f"insufficient shared-drive free space: {free} bytes",
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
            if target.is_file() and target.stat().st_size == size and digest(target) == expected_hash:
                row["status"] = "verified_existing"
            else:
                url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/UD-Q4_K_XL/{name}"
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
    print(f"Qwen3.8 UD-Q4_K_XL download {state['status']}: {state.get('error', '')}", flush=True)
    return 0 if state["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
