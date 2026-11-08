#!/usr/bin/env python3
"""Guarded Qwen3.8 Q4 two-chat fit at distinct occupied depths."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from run_strata_q4_smoke import (CONTROL, COMPONENTS, DATA, MODEL, PACK,
                                  block, gpu, memory, request, save, stamp)

PORT = 18144
WORDS = {'chat_a': 'ORCHID', 'chat_b': 'LANTERN'}
LINES = {'chat_a': 64, 'chat_b': 192}


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
    ap.add_argument('--parallel', type=int, choices=(2,), default=2)
    args = ap.parse_args()
    words = dict(list(WORDS.items())[:args.parallel])
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    state = {'model': str(MODEL), 'pack': str(PACK), 'context': 8192,
             'parallel': args.parallel, 'gpu': 0, 'resident_experts_gib': 8,
             'admission_model': 'two slots reserved at launch; chats opened sequentially',
             'live_chat_state_location': 'not established by this runner',
             'started_at': stamp(), 'status': 'running', 'requests': [], 'admissions': []}
    save(out / 'checkpoint.json', state)
    env = dict(os.environ, STRATA_COMPONENTS_DIR=str(COMPONENTS), CUDA_DEVICE_ORDER='PCI_BUS_ID')
    common = [str(CONTROL), 'launch', '--family', 'unsloth', '--model', 'ud-q4_k_xl',
              '--model-path', str(MODEL), '--data-dir', str(DATA), '--gpu', '0',
              '--backend', 'nvidia', '--context', '8192', '--kv', 'int8',
              '--vision', 'off', '--parallel', str(args.parallel), '--mtp', 'off', '--drafting', 'off',
              '--set', 'resident-budget-gib=8', '--set', 'vram-reserve-mib=768',
              '--tune', 'skip', '--port', str(PORT), '--access', 'local',
              '--no-api-key', '--yes', '--output', 'json']
    launched = False

    def terminated(_signum, _frame):
        raise RuntimeError('multichat terminated by Manager or memory guard')
    signal.signal(signal.SIGTERM, terminated)
    try:
        if not (PACK / 'index.txt').is_file() or not (PACK / 'native_experts.txt').is_file():
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
        state['host_loaded'] = memory()
        state['gpu_loaded_mib'] = gpu()
        if state['host_loaded']['MemAvailable_kib'] < 4 * 1048576:
            raise RuntimeError('less than 4 GiB MemAvailable after load')
        histories = {}
        for chat, word in words.items():
            before = {'host': memory(), 'gpu_mib': gpu(), 'block': block()}
            first = first_prompt(word, LINES[chat])
            messages = [{'role': 'user', 'content': first}]
            result = call(out, f'{chat}_first', messages, word)
            state['requests'].append(result)
            if not result['correct']:
                raise RuntimeError(f'{chat} first answer mismatch')
            histories[chat] = messages + [{'role': 'assistant', 'content': result['answer']},
                                         {'role': 'user', 'content': 'What is this conversation\'s private code word? Reply with only that uppercase word.'}]
            after = {'host': memory(), 'gpu_mib': gpu(), 'block': block()}
            state['admissions'].append({'chat': chat, 'filler_lines': LINES[chat],
                                        'prompt_chars': len(first), 'prompt_tokens': (result.get('usage') or {}).get('prompt_tokens'),
                                        'before': before, 'after': after})
            if after['host']['MemAvailable_kib'] < 4 * 1048576:
                raise RuntimeError(f'less than 4 GiB MemAvailable after admitting {chat}')
            for older, older_word in words.items():
                if older not in histories:
                    continue
                continued = call(out, f'{older}_after_{chat}', histories[older], older_word)
                state['requests'].append(continued)
                if not continued['correct']:
                    raise RuntimeError(f'{older} continuation mismatch after admitting {chat}')
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
