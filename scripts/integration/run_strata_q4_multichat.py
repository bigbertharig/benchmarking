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

from tier_trace import mark as trace_mark
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


def trace_event(phase, event, details=None):
    directory = os.environ.get('TIER_TRACE_DIR')
    if directory:
        trace_mark(Path(directory), phase, event, details)


def call(out, name, messages, expected):
    trace_event(name, 'begin', {'chat_messages': len(messages)})
    start = time.monotonic()
    response = request('/v1/chat/completions', {
        'model': 'strata', 'messages': messages, 'max_tokens': 96, 'temperature': 0}, timeout=1200)
    wall = round(time.monotonic() - start, 3)
    save(out / f'{name}_response.json', response)
    trace_event(name, 'end', {'usage': response.get('usage'), 'timings': response.get('timings')})
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
    ap.add_argument('--context', type=int, choices=(8192, 32768), default=8192)
    ap.add_argument('--lines-a', type=int, default=64)
    ap.add_argument('--lines-b', type=int, default=192)
    ap.add_argument('--stop-after', action='store_true', help='explicitly stop Strata after a successful run')
    ap.add_argument('--reuse-loaded', action='store_true', help='use an already healthy matching Strata load')
    args = ap.parse_args()
    if args.reuse_loaded and args.stop_after:
        ap.error('--reuse-loaded cannot be combined with --stop-after')
    words = dict(list(WORDS.items())[:args.parallel])
    lines = {'chat_a': args.lines_a, 'chat_b': args.lines_b}
    if min(lines.values()) < 1 or max(lines.values()) > 1500:
        ap.error('filler line counts must be between 1 and 1500')
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    state = {'model': str(MODEL), 'pack': str(PACK), 'context': args.context,
             'parallel': args.parallel, 'gpu': 0, 'resident_experts_gib': 8,
             'admission_model': 'two slots reserved at launch; chats opened sequentially',
             'live_chat_state_location': 'not established by this runner',
             'started_at': stamp(), 'status': 'running', 'requests': [], 'admissions': [],
             'end_state_requested': 'stop' if args.stop_after else 'freeze'}
    save(out / 'checkpoint.json', state)
    env = dict(os.environ, STRATA_COMPONENTS_DIR=str(COMPONENTS), CUDA_DEVICE_ORDER='PCI_BUS_ID')
    common = [str(CONTROL), 'launch', '--family', 'unsloth', '--model', 'ud-q4_k_xl',
              '--model-path', str(MODEL), '--data-dir', str(DATA), '--gpu', '0',
              '--backend', 'nvidia', '--context', str(args.context), '--kv', 'int8',
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
        if args.reuse_loaded:
            if state['gpu_before_mib'].get(0, 0) < 1024:
                raise RuntimeError('GPU0 has no resident Strata load to reuse')
            config_path = Path.home() / '.local/state/strata/launch' / f'ud-q4_k_xl-{args.context // 1024}k.json'
            config = json.loads(config_path.read_text())
            engine_args = config.get('args', [])
            expected = {'--pack': str(PACK), '--max-context': str(args.context),
                        '--kv': 'int8', '--resident-budget-gib': '8', '--vram-reserve-mib': '768'}
            for flag, value in expected.items():
                if flag not in engine_args or engine_args[engine_args.index(flag) + 1] != value:
                    raise RuntimeError(f'resident Strata config mismatch: {flag}')
            if config.get('gpu') != 0 or config.get('port') != PORT or config.get('drafting') != 'off':
                raise RuntimeError('resident Strata GPU, port, or drafting mismatch')
            health = request('/health', timeout=5)
            if (health.get('status') != 'ok' or not health.get('loaded')
                    or health.get('max_context') != args.context
                    or health.get('model') != 'qwen3.8-flash-next-unsloth-ud-q4_k_xl'):
                raise RuntimeError('resident Strata health mismatch')
            state['health'] = health
            state['reused_loaded'] = True
        else:
            if state['gpu_before_mib'].get(0, 999999) > 1024:
                raise RuntimeError('GPU0 is already occupied; use --reuse-loaded for a matching load')
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
            trace_event('load', 'begin')
            started = time.monotonic()
            launched = True
            launch = subprocess.run(common + ['--no-tui'], env=env, capture_output=True,
                                    text=True, timeout=1200)
            state['launch_seconds'] = round(time.monotonic() - started, 3)
            trace_event('load', 'end', {'launch_seconds': state['launch_seconds']})
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
            first = first_prompt(word, lines[chat])
            messages = [{'role': 'user', 'content': first}]
            result = call(out, f'{chat}_first', messages, word)
            state['requests'].append(result)
            if not result['correct']:
                raise RuntimeError(f'{chat} first answer mismatch')
            histories[chat] = messages + [{'role': 'assistant', 'content': result['answer']},
                                         {'role': 'user', 'content': 'What is this conversation\'s private code word? Reply with only that uppercase word.'}]
            after = {'host': memory(), 'gpu_mib': gpu(), 'block': block()}
            state['admissions'].append({'chat': chat, 'filler_lines': lines[chat],
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
        if state['status'] == 'passed' and not args.stop_after:
            state['kept_loaded'] = True
        if launched and not state.get('kept_loaded'):
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
