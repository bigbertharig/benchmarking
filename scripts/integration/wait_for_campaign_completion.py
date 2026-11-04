#!/usr/bin/env python3
"""Wait for a managed benchmark campaign's terminal status without polling the rig.

The campaign writes status.json with an atomic rename. Linux inotify wakes this
process on that rename; a 30-minute fallback read covers filesystems that do not
forward inotify events. Exit 0 only when every campaign block completed.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import select
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
EVENT = struct.Struct("iIII")
TERMINAL = {"completed", "completed_with_failures", "failed", "interrupted"}


def read_status(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def alert(path: Path, state: dict) -> int:
    blocks = state.get("blocks") or {}
    result = {
        "event": "CAMPAIGN_COMPLETION_ALERT",
        "campaign": state.get("campaign"),
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "completed_blocks": sum(x.get("status") == "completed" for x in blocks.values()),
        "total_blocks": len(blocks),
        "failed_blocks": [name for name, x in blocks.items() if x.get("status") == "failed"],
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "receipt": str(path),
    }
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if state.get("status") == "completed" else 1



def alert_capacity(path: Path, state: dict) -> int:
    ok = not state.get("error") and state.get("fits") is not False and bool(state.get("load")) and bool(state.get("short_probe"))
    result = {
        "event": "CAPACITY_COMPLETION_ALERT",
        "model": state.get("model"),
        "status": "completed" if ok else "failed",
        "context": (state.get("plan") or {}).get("ctx"),
        "gpus": state.get("cards"),
        "depth_probes": len(state.get("depth_probes") or []),
        "error": state.get("error"),
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "receipt": str(path),
    }
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if ok else 1

def alert_terminal(path: Path, state: dict) -> int:
    ok = state.get("status") == "passed"
    result = {"event": "BENCHMARK_TERMINAL_ALERT", "status": state.get("status"),
              "model": state.get("model"), "modes": {name: row.get("status")
              for name, row in (state.get("modes") or {}).items()},
              "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "receipt": str(path)}
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("status", type=Path, help="campaign history/<name>/<run-id>/status.json")
    ap.add_argument("--kind", choices=("campaign", "capacity", "terminal"), default="campaign",
                    help="receipt format (default: campaign)")
    ap.add_argument("--fallback-seconds", type=int, default=1800,
                    help="inotify fallback check interval (default: 30 minutes)")
    args = ap.parse_args()
    if args.fallback_seconds < 1:
        ap.error("--fallback-seconds must be positive")
    path = args.status.resolve()
    if not path.parent.is_dir():
        ap.error(f"status directory does not exist: {path.parent}")
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "inotify_init1")
    try:
        wd = libc.inotify_add_watch(fd, os.fsencode(path.parent),
                                    IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE)
        if wd < 0:
            raise OSError(ctypes.get_errno(), f"inotify_add_watch {path.parent}")
        while True:
            state = read_status(path)
            if state and args.kind == "campaign" and state.get("status") in TERMINAL:
                return alert(path, state)
            if state and args.kind == "capacity" and state.get("kind") == "capacity":
                return alert_capacity(path, state)
            if state and args.kind == "terminal" and state.get("status") in ("passed", "failed"):
                return alert_terminal(path, state)
            ready, _, _ = select.select([fd], [], [], args.fallback_seconds)
            if not ready:
                continue
            try:
                buf = os.read(fd, 65536)
            except BlockingIOError:
                continue
            offset = 0
            while offset + EVENT.size <= len(buf):
                _, _, _, name_len = EVENT.unpack_from(buf, offset)
                start = offset + EVENT.size
                name = buf[start:start + name_len].split(b"\0", 1)[0]
                offset = start + name_len
                if name == os.fsencode(path.name):
                    break
    finally:
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())
