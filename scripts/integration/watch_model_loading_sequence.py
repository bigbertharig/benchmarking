#!/usr/bin/env python3
"""Emit one alert per completed model-loading stage, then the terminal result."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import select
import struct
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments/model_loading_sequences')
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
EVENT = struct.Struct('iIII')


def load(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('run_id')
    args = ap.parse_args()
    folder = ROOT / args.run_id
    if not folder.is_dir():
        ap.error(f'run folder missing: {folder}')
    seen = set()

    def emit():
        for path in sorted(folder.glob('*.json')):
            if path.name in ('manifest.json', 'terminal.json'):
                continue
            row = load(path)
            if not row or row.get('status') not in ('passed', 'failed'):
                continue
            key = (path.name, row.get('finished_at'))
            if key in seen:
                continue
            seen.add(key)
            print(json.dumps({'event': 'STAGE_FINISHED', 'run_id': args.run_id,
                              'stage': row.get('id'), 'status': row['status'],
                              'error': row.get('error'), 'receipt': str(path),
                              'observed_at': datetime.now(timezone.utc).isoformat()}), flush=True)
        terminal = load(folder / 'terminal.json')
        if terminal:
            print(json.dumps({'event': 'SEQUENCE_FINISHED', 'run_id': args.run_id,
                              'status': terminal.get('status'), 'reason': terminal.get('reason'),
                              'stages': terminal.get('stages'),
                              'receipt': str(folder / 'terminal.json'),
                              'observed_at': datetime.now(timezone.utc).isoformat()}), flush=True)
            return True
        return False

    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if fd < 0:
        raise OSError(ctypes.get_errno(), 'inotify_init1')
    try:
        wd = libc.inotify_add_watch(fd, os.fsencode(folder), IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE)
        if wd < 0:
            raise OSError(ctypes.get_errno(), f'inotify_add_watch {folder}')
        while True:
            if emit():
                return 0
            ready, _, _ = select.select([fd], [], [], 1800)
            if ready:
                try:
                    os.read(fd, 65536)
                except BlockingIOError:
                    pass
    finally:
        os.close(fd)


if __name__ == '__main__':
    raise SystemExit(main())
