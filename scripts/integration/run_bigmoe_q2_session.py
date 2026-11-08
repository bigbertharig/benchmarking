#!/usr/bin/env python3
"""Probe one BigMoe Q2 session across continuing and replaced conversations."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from run_bigmoe_q2_smoke import CLI, MODEL
from run_strata_q4_smoke import block, gpu, memory, save, stamp


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(CLI), '-m', str(MODEL), '--session', '--chatml', '--no-think',
           '-c', '8192', '-n', '8', '--moe-stream', '--cache-mb', '8192',
           '--dense-mapped', 'token_embd.weight;per_layer_token_embd.weight',
           '--no-cache-pin', '--gpu-layers', '0']
    state = {'status': 'running', 'started_at': stamp(), 'command': cmd,
             'model': str(MODEL), 'version': '0.40.1', 'turns': []}
    save(out / 'checkpoint.json', state)
    proc = None

    def terminated(_signum, _frame):
        raise RuntimeError('BigMoe session terminated by Manager')
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
        state['host_min_available_kib'] = before
        stdout_path = out / 'stdout.txt'
        stderr_path = out / 'stderr.txt'
        with stdout_path.open('w') as stdout, stderr_path.open('w') as stderr:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=stdout,
                                    stderr=stderr, text=True, start_new_session=True)
            offset = 0
            def wait_event(kind, ident=None, timeout=900):
                nonlocal offset
                start = time.monotonic()
                while time.monotonic() - start < timeout:
                    available = memory()['MemAvailable_kib']
                    state['host_min_available_kib'] = min(state['host_min_available_kib'], available)
                    if available < 4 * 1048576 or before - available > int(26_000_000_000 / 1024):
                        raise RuntimeError('host memory guard tripped')
                    with stdout_path.open(errors='replace') as stream:
                        stream.seek(offset)
                        lines = stream.readlines()
                        offset = stream.tell()
                        for line in lines:
                            if line.startswith('BMOE_ERROR '):
                                error = json.loads(line[len('BMOE_ERROR '):])
                                raise RuntimeError(f'BigMoe error: {error}')
                            if line.startswith(kind + ' '):
                                value = json.loads(line[len(kind)+1:])
                                if ident is None or value.get('id') == ident:
                                    return value
                    if proc.poll() is not None:
                        raise RuntimeError(f'BigMoe exited {proc.returncode} before {kind} {ident}')
                    time.sleep(2)
                raise RuntimeError(f'timed out waiting for {kind} {ident}')
            state['ready'] = wait_event('BMOE_READY', timeout=600)
            save(out / 'checkpoint.json', state)
            cases = [
                (1, 'a_first', 'Reply with exactly the single uppercase word ORCHID.', True, 'ORCHID'),
                (2, 'a_continue', 'Repeat your previous answer as one uppercase word.', False, 'ORCHID'),
                (3, 'b_first', 'Reply with exactly the single uppercase word LANTERN.', True, 'LANTERN'),
                (4, 'b_continue', 'Repeat your previous answer as one uppercase word.', False, 'LANTERN'),
                (5, 'a_reopen', 'Reply with exactly the single uppercase word ORCHID.', True, 'ORCHID'),
            ]
            for ident, name, prompt, clear_kv, expected in cases:
                proc.stdin.write(json.dumps({'cmd': 'generate', 'id': ident, 'prompt': prompt,
                                             'n_predict': 8, 'think': False,
                                             'clear_kv': clear_kv}) + '\n')
                proc.stdin.flush()
                done = wait_event('BMOE_DONE', ident, timeout=900)
                answer = (done.get('text') or '').strip()
                row = {'name': name, 'id': ident, 'clear_kv': clear_kv,
                       'expected': expected, 'answer': answer, 'correct': answer == expected,
                       'done': done, 'host_after': memory()}
                state['turns'].append(row)
                save(out / 'checkpoint.json', state)
                if not row['correct']:
                    raise RuntimeError(f'{name}: expected {expected}, got {answer!r}')
            proc.stdin.write('{"cmd":"close"}\n')
            proc.stdin.flush()
            proc.stdin.close()
            proc.wait(timeout=60)
            state['exit_code'] = proc.returncode
            if proc.returncode:
                raise RuntimeError(f'BigMoe session exited {proc.returncode}')
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
