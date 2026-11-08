#!/usr/bin/env python3
"""Guarded Qwen3.8 Q2 RAM-KV streaming beyond the 32K resident window."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from run_strata_q4_smoke import CONTROL, COMPONENTS, block, gpu, memory, request, save, stamp

MODEL = Path('/data/model-hotset/qwen3.8-flash-next-q2_0')
DATA = Path('/data/bench-staging/strata-v0.2.10/data')
PACK = DATA / 'packs/q2_0'
PORT = 18144
WORD = 'ORCHID'
LINES = 2800


def first_prompt(word, line_count):
    filler = '\n'.join(f'Reference line {i:04d}: the ordinary ledger remains unchanged.'
                       for i in range(line_count))
    return (f'The private code word for this conversation is {word}. Remember it.\n'
            f'{filler}\nWhat is this conversation\'s private code word? '
            'Reply with only that uppercase word.')


def call(out, name, messages, expected):
    start = time.monotonic()
    response = request('/v1/chat/completions', {
        'model': 'strata', 'messages': messages, 'max_tokens': 96, 'temperature': 0}, timeout=600)
    wall = round(time.monotonic() - start, 3)
    save(out / f'{name}_response.json', response)
    choice = (response.get('choices') or [{}])[0]
    message = choice.get('message') or {}
    answer = (message.get('content') or '').strip()
    final = answer.rsplit('</think>', 1)[-1].strip() if '</think>' in answer else answer
    return {'name': name, 'wall_seconds': wall, 'answer': final[:200],
            'expected': expected, 'correct': final == expected,
            'usage': response.get('usage'), 'timings': response.get('timings'),
            'finish_reason': choice.get('finish_reason')}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    state = {'model': str(MODEL), 'pack': str(PACK), 'context': 65536,
             'parallel': 1, 'gpu': 0, 'kv_resident': 32768,
             'resident_experts_gib': 8, 'prompt_lines': LINES,
             'started_at': stamp(), 'status': 'running', 'requests': []}
    save(out / 'checkpoint.json', state)
    env = dict(os.environ, STRATA_COMPONENTS_DIR=str(COMPONENTS), CUDA_DEVICE_ORDER='PCI_BUS_ID')
    common = [str(CONTROL), 'launch', '--family', 'qwen', '--model', 'q2_0',
              '--model-path', str(MODEL), '--data-dir', str(DATA), '--gpu', '0',
              '--backend', 'nvidia', '--context', '65536', '--kv', 'int8',
              '--vision', 'off', '--parallel', '1', '--mtp', 'off', '--drafting', 'off',
              '--set', 'resident-budget-gib=8', '--set', 'vram-reserve-mib=768',
              '--set', 'kv-resident=32768',
              '--tune', 'skip', '--port', str(PORT), '--access', 'local',
              '--no-api-key', '--yes', '--output', 'json']
    launched = False

    def terminated(_signum, _frame):
        raise RuntimeError('multichat terminated by Manager or memory guard')
    signal.signal(signal.SIGTERM, terminated)
    try:
        if not (PACK / 'index.txt').is_file() or not (PACK / 'experts.bin').is_file():
            raise RuntimeError('Q2 pack completion markers missing')
        if len(list(MODEL.glob('*.gguf'))) != 2:
            raise RuntimeError('expected two Q2 GGUF shards')
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
                                text=True, timeout=1200)
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
        state['engine_commands'] = []
        for proc_path in Path('/proc').iterdir():
            if not proc_path.name.isdigit():
                continue
            try:
                args_line = (proc_path / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            except (OSError, PermissionError):
                continue
            if '--kv-resident' in args_line and 'strata' in args_line:
                state['engine_commands'].append(args_line[:2000])
        if not any('--kv-resident 32768' in item or '--kv-resident=32768' in item
                   for item in state['engine_commands']):
            raise RuntimeError('running engine command lacks expected KV resident window')
        state['host_loaded'] = memory()
        state['gpu_loaded_mib'] = gpu()
        if state['host_loaded']['MemAvailable_kib'] < 4 * 1048576:
            raise RuntimeError('less than 4 GiB MemAvailable after load')
        first = first_prompt(WORD, LINES)
        messages = [{'role': 'user', 'content': first}]
        result = call(out, 'long_first', messages, WORD)
        state['requests'].append(result)
        if not result['correct']:
            raise RuntimeError('long first answer mismatch')
        occupied = (result.get('usage') or {}).get('prompt_tokens')
        if not isinstance(occupied, int) or occupied <= 32768 or occupied >= 65536:
            raise RuntimeError(f'prompt did not occupy streaming window: {occupied}')
        state['after_first'] = {'host': memory(), 'gpu_mib': gpu(), 'block': block(),
                                'prompt_chars': len(first), 'prompt_tokens': occupied}
        if state['after_first']['host']['MemAvailable_kib'] < 4 * 1048576:
            raise RuntimeError('less than 4 GiB MemAvailable after long prompt')
        history = messages + [{'role': 'assistant', 'content': result['answer']},
                              {'role': 'user', 'content': 'What is this conversation\'s private code word? Reply with only that uppercase word.'}]
        continued = call(out, 'long_followup', history, WORD)
        state['requests'].append(continued)
        if not continued['correct']:
            raise RuntimeError('long continuation mismatch')
        state['after_followup'] = {'host': memory(), 'gpu_mib': gpu(), 'block': block()}
        save(out / 'checkpoint.json', state)
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
