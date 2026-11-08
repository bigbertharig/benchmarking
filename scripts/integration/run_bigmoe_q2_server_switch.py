#!/usr/bin/env python3
"""Probe A/B/A conversation switching through one BigMoe HTTP server load."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from run_strata_q4_smoke import block, gpu, memory, save, stamp

SERVER = Path('/data/bench-staging/bigmoe-v0.40.1/bmoe-server')
MODEL = Path('/data/model-hotset/qwen3.8-flash-next-q2_0/Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00001-of-00002.gguf')
PORT = 18765
BASE = f'http://127.0.0.1:{PORT}'


def get(path, timeout=10):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as response:
        return json.load(response)


def post(path, body, timeout=900):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def events(path):
    output = []
    kind = None
    for line in path.read_text(errors='replace').splitlines():
        if line.startswith('event: '):
            kind = line[7:].strip()
        elif line.startswith('data: '):
            if kind == 'done':
                try:
                    output.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
            kind = None
    return output


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    data_dir = Path('/data/bench-staging/bigmoe-server-switch-20261108')
    cmd = [str(SERVER), '--host', '127.0.0.1', '--port', str(PORT),
           '--data-dir', str(data_dir), '--chat-only', '-m', str(MODEL),
           '-c', '8192', '-n', '8', '--no-think', '--moe-stream',
           '--cache-mb', '8192', '--dense-mapped',
           'token_embd.weight;per_layer_token_embd.weight',
           '--no-cache-pin', '--gpu-layers', '0']
    state = {'status': 'running', 'started_at': stamp(), 'command': cmd,
             'model': str(MODEL), 'bigmoe_version': '0.40.1', 'turns': []}
    save(out / 'checkpoint.json', state)
    server = listener = None

    def terminated(_signum, _frame):
        raise RuntimeError('BigMoe server probe terminated by Manager')
    signal.signal(signal.SIGTERM, terminated)
    try:
        if not SERVER.is_file() or not MODEL.is_file():
            raise RuntimeError('BigMoe server or Q2 model missing')
        state['host_before'] = memory()
        state['gpu_before_mib'] = gpu()
        state['block_before'] = block()
        before = state['host_before']['MemAvailable_kib']
        if before < 8 * 1048576:
            raise RuntimeError('less than 8 GiB MemAvailable before start')
        state['host_min_available_kib'] = before
        with (out / 'server_stdout.txt').open('w') as stdout, (out / 'server_stderr.txt').open('w') as stderr:
            server = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, start_new_session=True)
            began = time.monotonic()
            while time.monotonic() - began < 600:
                if server.poll() is not None:
                    raise RuntimeError(f'BigMoe server exited {server.returncode} during load')
                available = memory()['MemAvailable_kib']
                state['host_min_available_kib'] = min(state['host_min_available_kib'], available)
                if available < 4 * 1048576 or before - available > int(26_000_000_000 / 1024):
                    raise RuntimeError('host memory floor or 26 GB drop ceiling reached')
                try:
                    info = get('/api/info', timeout=2)
                    if info.get('state') == 'ready':
                        state['ready'] = info
                        state['load_wall_seconds'] = round(time.monotonic() - began, 3)
                        break
                    if info.get('state') == 'error':
                        raise RuntimeError(f'BigMoe server load error: {info.get("error")}')
                except (OSError, urllib.error.URLError, json.JSONDecodeError):
                    pass
                time.sleep(2)
            else:
                raise RuntimeError('BigMoe server ready timeout')
            if not state['ready'].get('model', {}).get('streaming'):
                raise RuntimeError('server did not enable expert streaming')
            event_file = out / 'events.txt'
            with event_file.open('w') as stream:
                listener = subprocess.Popen(['curl', '-Ns', '--max-time', '1200',
                                             BASE + '/api/events'], stdout=stream,
                                            stderr=subprocess.DEVNULL, start_new_session=True)
                time.sleep(2)
                a_first = 'Reply with exactly the single uppercase word ORCHID.'
                b_first = 'Reply with exactly the single uppercase word LANTERN.'
                cases = [
                    ('a_first', [{'role': 'user', 'content': a_first}], 'ORCHID'),
                    ('b_first', [{'role': 'user', 'content': b_first}], 'LANTERN'),
                    ('a_reopen', [{'role': 'user', 'content': a_first},
                                  {'role': 'assistant', 'content': 'ORCHID'},
                                  {'role': 'user', 'content': 'Repeat the uppercase word from this chat.'}], 'ORCHID'),
                    ('a_continue', [{'role': 'user', 'content': a_first},
                                    {'role': 'assistant', 'content': 'ORCHID'},
                                    {'role': 'user', 'content': 'Repeat the uppercase word from this chat.'},
                                    {'role': 'assistant', 'content': 'ORCHID'},
                                    {'role': 'user', 'content': 'What uppercase word belongs to this chat?'}], 'ORCHID'),
                ]
                for name, messages, expected in cases:
                    started = time.monotonic()
                    response = post('/v1/chat/completions', {
                        'model': 'bigmoe', 'messages': messages, 'max_tokens': 8,
                        'think': False, 'stream': False})
                    wall = round(time.monotonic() - started, 3)
                    save(out / f'{name}_response.json', response)
                    choice = (response.get('choices') or [{}])[0]
                    answer = ((choice.get('message') or {}).get('content') or '').strip()
                    row = {'name': name, 'expected': expected, 'answer': answer,
                           'correct': answer == expected, 'wall_seconds': wall,
                           'usage': response.get('usage'), 'host_after': memory()}
                    state['host_min_available_kib'] = min(state['host_min_available_kib'],
                                                          row['host_after']['MemAvailable_kib'])
                    state['turns'].append(row)
                    save(out / 'checkpoint.json', state)
                    if not row['correct']:
                        raise RuntimeError(f'{name}: expected {expected}, got {answer!r}')
                    if row['host_after']['MemAvailable_kib'] < 4 * 1048576:
                        raise RuntimeError('host memory fell below 4 GiB')
                time.sleep(2)
                state['done_events'] = events(event_file)
            if len(state['done_events']) < len(cases):
                raise RuntimeError(f'only {len(state["done_events"])} done events for {len(cases)} turns')
            for row, event in zip(state['turns'], state['done_events'][-len(cases):]):
                row['done'] = event
            state['status'] = 'passed'
    except BaseException as exc:
        state['status'] = 'failed'
        state['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        for process in (listener, server):
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
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
