#!/usr/bin/env python3
"""Guarded one-card Qwen3.8 UD-Q4_K_XL 8K launch and answer smoke."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STRATA = Path('/data/bench-staging/strata-v0.2.10')
CONTROL = STRATA / 'control/bin/strata'
COMPONENTS = STRATA / 'components'
MODEL = Path('/data/model-hotset/qwen3.8-flash-next-ud-q4_k_xl')
DATA = MODEL / 'runtime/strata-ud-q4_k_xl'
PACK = DATA / 'packs/ud-q4_k_xl'
PORT = 18144
PROMPT = 'Reply with the single word ORCHID. Do not include any other text.'


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    os.replace(temp, path)


def memory():
    out = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, _, value = line.partition(':')
        if key in ('MemAvailable', 'SwapFree', 'SwapTotal'):
            out[key + '_kib'] = int(value.split()[0])
    return out


def gpu():
    result = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used',
                             '--format=csv,noheader,nounits'], capture_output=True,
                            text=True, check=True)
    return {int(parts[0].strip()): int(parts[1].strip()) for line in result.stdout.splitlines()
            if len(parts := line.split(',')) == 2}


def block():
    out = {}
    for name, path in [('nvme', Path('/sys/block/nvme0n1/stat')),
                       ('sata', Path('/sys/block/sda/stat'))]:
        parts = [int(x) for x in path.read_text().split()]
        out[name] = {'read_bytes': parts[2] * 512, 'write_bytes': parts[6] * 512}
    return out


def request(path, body=None, timeout=10):
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}', data=payload,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    state = {'model': str(MODEL), 'pack': str(PACK), 'context': 8192,
             'gpu': 0, 'resident_experts_gib': 8, 'mtp': 'off',
             'started_at': stamp(), 'status': 'running', 'prompt': PROMPT}
    save(out / 'checkpoint.json', state)
    env = dict(os.environ, STRATA_COMPONENTS_DIR=str(COMPONENTS), CUDA_DEVICE_ORDER='PCI_BUS_ID')
    common = [str(CONTROL), 'launch', '--family', 'unsloth', '--model', 'ud-q4_k_xl',
              '--model-path', str(MODEL), '--data-dir', str(DATA), '--gpu', '0',
              '--backend', 'nvidia', '--context', '8192', '--kv', 'int8',
              '--vision', 'off', '--parallel', '1', '--mtp', 'off', '--drafting', 'off',
              '--set', 'resident-budget-gib=8', '--tune', 'skip', '--port', str(PORT),
              '--access', 'local', '--no-api-key', '--yes', '--output', 'json']
    launched = False
    def terminated(_signum, _frame):
        raise RuntimeError('smoke terminated by Manager or memory guard')
    signal.signal(signal.SIGTERM, terminated)
    try:
        if not (PACK / 'native_experts.txt').is_file() or not (PACK / 'index.txt').is_file():
            raise RuntimeError('Q4 pack completion markers missing')
        if (PACK / 'experts.bin').exists():
            raise RuntimeError('unexpected experts.bin duplicate')
        if len(list(MODEL.glob('*.gguf'))) != 4:
            raise RuntimeError('expected four Q4 GGUF shards')
        state['host_before'] = memory()
        state['gpu_before_mib'] = gpu()
        state['block_before'] = block()
        if state['host_before']['MemAvailable_kib'] < 8 * 1048576:
            raise RuntimeError('less than 8 GiB MemAvailable before load')
        if state['gpu_before_mib'].get(0, 999999) > 1024:
            raise RuntimeError('GPU0 is already occupied')
        plan = subprocess.run(common + ['--plan'], env=env, capture_output=True,
                              text=True, timeout=120)
        (out / 'plan_stdout.json').write_text(plan.stdout)
        (out / 'plan_stderr.txt').write_text(plan.stderr)
        if plan.returncode:
            raise RuntimeError(f'Strata plan exited {plan.returncode}')
        plan_data = json.loads(plan.stdout)
        download = plan_data.get('plan', {}).get('download', {})
        state['plan'] = {'ok': plan_data.get('ok'), 'download': download,
                         'warnings': plan_data.get('plan', {}).get('warnings', [])}
        if not plan_data.get('ok') or not download.get('engine_usable') or download.get('gb') != 0:
            raise RuntimeError('plan requires missing engine or model download')
        save(out / 'checkpoint.json', state)
        start = time.monotonic()
        launched = True
        launch = subprocess.run(common + ['--no-tui'], env=env, capture_output=True,
                                text=True, timeout=1200)
        state['launch_seconds'] = round(time.monotonic() - start, 3)
        state['launch_exit'] = launch.returncode
        (out / 'launch_stdout.txt').write_text(launch.stdout)
        (out / 'launch_stderr.txt').write_text(launch.stderr)
        if launch.returncode:
            raise RuntimeError(f'Strata launch exited {launch.returncode}')
        for _ in range(30):
            try:
                state['health'] = request('/health', timeout=2)
                break
            except (OSError, ValueError):
                time.sleep(2)
        else:
            raise RuntimeError('Strata did not become ready')
        state['host_loaded'] = memory()
        state['gpu_loaded_mib'] = gpu()
        if state['host_loaded']['MemAvailable_kib'] < 4 * 1048576:
            raise RuntimeError('less than 4 GiB MemAvailable after load')
        delta = (state['host_before']['MemAvailable_kib'] - state['host_loaded']['MemAvailable_kib']) * 1024
        state['host_available_drop_bytes'] = delta
        if delta > 26_000_000_000:
            raise RuntimeError('host available-memory drop exceeds 26 GB ceiling')
        before = block()
        start = time.monotonic()
        response = request('/v1/chat/completions', {'model': 'strata', 'messages': [
            {'role': 'user', 'content': PROMPT}], 'max_tokens': 512, 'temperature': 0}, timeout=1200)
        wall = round(time.monotonic() - start, 3)
        save(out / 'response.json', response)
        choice = (response.get('choices') or [{}])[0]
        message = choice.get('message') or {}
        answer = (message.get('content') or '').strip()
        reasoning = (message.get('reasoning_content') or '').strip()
        final = answer.rsplit('</think>', 1)[-1].strip() if '</think>' in answer else answer
        state['request'] = {'wall_seconds': wall, 'usage': response.get('usage'),
                            'finish_reason': choice.get('finish_reason'),
                            'answer': answer[:500], 'reasoning_tail': reasoning[-250:],
                            'final_answer': final[:200], 'correct': final == 'ORCHID',
                            'block_before': before, 'block_after': block(),
                            'host_after': memory(), 'gpu_after_mib': gpu()}
        if not state['request']['correct']:
            raise RuntimeError('8K functional answer did not produce visible ORCHID')
        if state['request']['host_after']['MemAvailable_kib'] < 4 * 1048576:
            raise RuntimeError('less than 4 GiB MemAvailable after request')
        state['status'] = 'passed'
    except BaseException as exc:
        state['status'] = 'failed'
        state['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if launched:
            try:
                stopped = subprocess.run([str(CONTROL), 'launch', '--stop', '--output', 'json'],
                                         env=env, capture_output=True, text=True, timeout=120)
                state['stop_exit'] = stopped.returncode
                (out / 'stop_stdout.txt').write_text(stopped.stdout)
                (out / 'stop_stderr.txt').write_text(stopped.stderr)
                if stopped.returncode:
                    state['status'] = 'failed'
                    state['error'] = f"Strata stop exited {stopped.returncode}"
            except Exception as exc:
                state['status'] = 'failed'
                state['stop_error'] = f'{type(exc).__name__}: {exc}'
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
