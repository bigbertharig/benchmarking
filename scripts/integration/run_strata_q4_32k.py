#!/usr/bin/env python3
"""Run guarded 32K Q4 Strata requests with reusable prompt and tier receipts."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from run_strata_q4_smoke import (CONTROL, COMPONENTS, DATA, MODEL, PACK, block,
                                  gpu, memory, request, save, stamp)

PORT = 18144
CONTEXT = 32768
SHORT = 'Reply with the single word ORCHID. Do not include any other text.'


def depth_prompt():
    # Fixed input for future same-file loader comparisons. Keep it in the receipt.
    rows = [f'Record {i:04d}: reference number {(i * 7919 + 104729) % 1000000:06d}.'
            for i in range(640)]
    rows[512] = 'Record 0512: the garden access word is MARIGOLD.'
    return ('Read the records below. What is the garden access word in record 0512? '
            'Reply with that single uppercase word.\n' + '\n'.join(rows))


def one_request(out, name, prompt, expected):
    before = {'host': memory(), 'gpu_mib': gpu(), 'block': block()}
    started = time.monotonic()
    response = request('/v1/chat/completions', {
        'model': 'strata', 'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 128, 'temperature': 0}, timeout=1500)
    elapsed = round(time.monotonic() - started, 3)
    save(out / f'{name}_response.json', response)
    choice = (response.get('choices') or [{}])[0]
    message = choice.get('message') or {}
    answer = (message.get('content') or '').strip()
    final = answer.rsplit('</think>', 1)[-1].strip() if '</think>' in answer else answer
    after = {'host': memory(), 'gpu_mib': gpu(), 'block': block()}
    return {'name': name, 'wall_seconds': elapsed, 'expected': expected,
            'answer': answer[:500], 'correct': final == expected,
            'finish_reason': choice.get('finish_reason'),
            'usage': response.get('usage'), 'timings': response.get('timings'),
            'before': before, 'after': after}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    prompts = {'short': SHORT, 'depth': depth_prompt()}
    save(out / 'prompts.json', prompts)
    state = {'model': str(MODEL), 'pack': str(PACK), 'context': CONTEXT,
             'gpu': 0, 'resident_experts_gib': 8, 'mtp': 'off',
             'started_at': stamp(), 'status': 'running', 'requests': []}
    save(out / 'checkpoint.json', state)
    env = dict(os.environ, STRATA_COMPONENTS_DIR=str(COMPONENTS), CUDA_DEVICE_ORDER='PCI_BUS_ID')
    common = [str(CONTROL), 'launch', '--family', 'unsloth', '--model', 'ud-q4_k_xl',
              '--model-path', str(MODEL), '--data-dir', str(DATA), '--gpu', '0',
              '--backend', 'nvidia', '--context', str(CONTEXT), '--kv', 'int8',
              '--vision', 'off', '--parallel', '1', '--mtp', 'off', '--drafting', 'off',
              '--set', 'resident-budget-gib=8', '--tune', 'skip', '--port', str(PORT),
              '--access', 'local', '--no-api-key', '--yes', '--output', 'json']
    launched = False

    def terminated(_signum, _frame):
        raise RuntimeError('32K run terminated by Manager or memory guard')
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
        started = time.monotonic()
        launched = True
        launch = subprocess.run(common + ['--no-tui'], env=env, capture_output=True,
                                text=True, timeout=1500)
        state['launch_seconds'] = round(time.monotonic() - started, 3)
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
        state['block_loaded'] = block()
        if state['health'].get('max_context') != CONTEXT:
            raise RuntimeError('health does not report requested 32K context')
        if state['host_loaded']['MemAvailable_kib'] < 4 * 1048576:
            raise RuntimeError('less than 4 GiB MemAvailable after load')
        for name, prompt, expected in [('short_first', SHORT, 'ORCHID'),
                                       ('short_repeat_1', SHORT, 'ORCHID'),
                                       ('short_repeat_2', SHORT, 'ORCHID'),
                                       ('depth_80pct', prompts['depth'], 'MARIGOLD')]:
            result = one_request(out, name, prompt, expected)
            state['requests'].append(result)
            save(out / 'checkpoint.json', state)
            if result['after']['host']['MemAvailable_kib'] < 4 * 1048576:
                raise RuntimeError(f'less than 4 GiB MemAvailable after {name}')
            if not result['correct']:
                raise RuntimeError(f'{name} answer mismatch')
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
                    state['error'] = f'Strata stop exited {stopped.returncode}'
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
