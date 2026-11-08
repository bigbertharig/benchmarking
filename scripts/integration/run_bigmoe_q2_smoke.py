#!/usr/bin/env python3
"""Bounded CPU/flash BigMoe Q2 correctness smoke before a Q4 comparison."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from run_strata_q4_smoke import block, gpu, memory, save, stamp

CLI = Path('/data/bench-staging/bigmoe-v0.40.1/bmoe-cli')
MODEL = Path('/data/model-hotset/qwen3.8-flash-next-q2_0/Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00001-of-00002.gguf')
PROMPT = 'Reply with the single word ORCHID. Do not include any other text.'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(CLI), '-m', str(MODEL), '-p', PROMPT, '--chatml', '--no-think',
           '-c', '8192', '-n', '64', '--moe-stream', '--cache-mb', '8192',
           '--dense-mapped', 'token_embd.weight;per_layer_token_embd.weight',
           '--no-cache-pin', '--gpu-layers', '0']
    state = {'status': 'running', 'started_at': stamp(), 'command': cmd,
             'model': str(MODEL), 'bigmoe_version': '0.40.1',
             'bigmoe_commit': '930b2c9ebd8c2cface6566bd9f11075ac07adfe0',
             'role': 'CPU/flash correctness gate; not a performance comparison'}
    save(out / 'checkpoint.json', state)
    proc = None
    def terminated(_signum, _frame):
        raise RuntimeError('BigMoe smoke terminated by Manager')
    signal.signal(signal.SIGTERM, terminated)
    try:
        if not CLI.is_file() or not MODEL.is_file():
            raise RuntimeError('BigMoe CLI or Q2 model missing')
        state['host_before'] = memory()
        state['gpu_before_mib'] = gpu()
        state['block_before'] = block()
        before = state['host_before']['MemAvailable_kib']
        if before < 8 * 1048576:
            raise RuntimeError('less than 8 GiB MemAvailable before start')
        floor = 4 * 1048576
        max_drop = int(26_000_000_000 / 1024)
        state['host_min_available_kib'] = before
        with (out / 'stdout.txt').open('w') as stdout, (out / 'stderr.txt').open('w') as stderr:
            proc = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, start_new_session=True)
            start = time.monotonic()
            while proc.poll() is None:
                available = memory()['MemAvailable_kib']
                state['host_min_available_kib'] = min(state['host_min_available_kib'], available)
                if available < floor or before - available > max_drop:
                    raise RuntimeError('host memory floor or 26 GB drop ceiling reached')
                if time.monotonic() - start > 1800:
                    raise RuntimeError('Q2 compatibility smoke timed out')
                time.sleep(2)
            state['wall_seconds'] = round(time.monotonic() - start, 3)
            state['exit_code'] = proc.returncode
        stdout = (out / 'stdout.txt').read_text(errors='replace')
        state['stdout_tail'] = stdout[-500:]
        state['stderr_tail'] = (out / 'stderr.txt').read_text(errors='replace')[-1000:]
        if proc.returncode:
            raise RuntimeError(f'BigMoe CLI exited {proc.returncode}')
        visible = stdout.split('\n\ngeneration:', 1)[0]
        if visible.startswith(PROMPT):
            visible = visible[len(PROMPT):]
        state['visible_answer'] = visible.strip()
        state['correct'] = state['visible_answer'] == 'ORCHID'
        if not state['correct']:
            raise RuntimeError('Q2 visible answer did not end with ORCHID')
        state['status'] = 'passed'
    except BaseException as exc:
        state['status'] = 'failed'
        state['error'] = f'{type(exc).__name__}: {exc}'
        if proc and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        state['exit_code'] = proc.returncode if proc else None
    finally:
        state['host_final'] = memory()
        state['gpu_final_mib'] = gpu()
        state['block_final'] = block()
        state['finished_at'] = stamp()
        save(out / 'terminal.json', state)
        print(json.dumps({'status': state['status'], 'error': state.get('error'),
                          'receipt': str(out / 'terminal.json')}), flush=True)
    return 0 if state['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
