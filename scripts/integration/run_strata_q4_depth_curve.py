#!/usr/bin/env python3
"""Qwen3.8 Q4 one-chat 16/32/50K occupied-depth baseline; freeze final load."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import shutil
import time
from pathlib import Path
from run_strata_q4_smoke import CONTROL, COMPONENTS, DATA, MODEL, PACK, block, gpu, memory, request, save, stamp
from tier_trace import mark

PORT = 18144
LINES = (1050, 1050, 1200)
TARGETS = (16000, 32000, 50000)

def event(phase, action, details=None):
    if os.environ.get('TIER_TRACE_DIR'):
        mark(Path(os.environ['TIER_TRACE_DIR']), phase, action, details)

def filler(start, count):
    return '\n'.join(f'Reference line {i:05d}: the ordinary ledger remains unchanged.'
                     for i in range(start, start + count))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--reuse-loaded', action='store_true')
    ap.add_argument('--restart-loaded', action='store_true')
    ap.add_argument('--resident-budget-gib', type=int, choices=(8, 12), default=8)
    ap.add_argument('--peer-device', action='store_true')
    ap.add_argument('--gpu-set', choices=('0','0,1','0,1,2,3','0,1,2,3,4,5'), default='0')
    ap.add_argument('--prefill', type=int, choices=(1024, 2048))
    ap.add_argument('--kv-resident', type=int, choices=(32768,))
    args = ap.parse_args()
    if args.peer_device and args.gpu_set != '0,1':
        ap.error('peer-device needs gpu-set 0,1')
    if args.reuse_loaded and args.restart_loaded:
        ap.error('reuse-loaded and restart-loaded are exclusive')
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    state = {'status': 'running', 'started_at': stamp(), 'model': str(MODEL),
             'context_cap': 65536, 'slots': 1, 'kv': 'int8',
             'resident_budget_gib': args.resident_budget_gib, 'peer_device': 1 if args.peer_device else None,
             'gpu_set': args.gpu_set, 'prefill': args.prefill,
             'chat_state_tier': 'ram_streamed' if args.kv_resident else 'gpu_vram',
             'targets': TARGETS, 'cases': [], 'end_state_requested': 'freeze'}
    save(out / 'checkpoint.json', state)
    env = dict(os.environ, STRATA_COMPONENTS_DIR=str(COMPONENTS), CUDA_DEVICE_ORDER='PCI_BUS_ID')
    common = [str(CONTROL), 'launch', '--family', 'unsloth', '--model', 'ud-q4_k_xl',
              '--model-path', str(MODEL), '--data-dir', str(DATA),
              '--gpu', args.gpu_set,
              '--backend', 'nvidia', '--context', '65536', '--kv', 'int8',
              '--vision', 'off', '--parallel', '1', '--mtp', 'off', '--drafting', 'off',
              '--set', f'resident-budget-gib={args.resident_budget_gib}',
              '--set', 'vram-reserve-mib=768',
              '--tune', 'skip', '--port', str(PORT), '--access', 'local',
              '--no-api-key', '--yes', '--output', 'json']
    if args.prefill:
        common += ['--set', f'prefill={args.prefill}']
    if args.kv_resident:
        common += ['--set', f'kv-resident={args.kv_resident}']
    if args.peer_device:
        common += ['--set', 'peer-device=1']
    stopped_existing = False
    new_healthy = False
    old_context = None
    try:
        if not (PACK / 'index.txt').is_file() or not (PACK / 'native_experts.txt').is_file():
            raise RuntimeError('Q4 pack markers missing')
        state['host_before'] = memory()
        state['gpu_before_mib'] = gpu()
        if state['host_before']['MemAvailable_kib'] < 8 * 1048576:
            raise RuntimeError('less than 8 GiB MemAvailable')
        if args.reuse_loaded:
            health = request('/health', timeout=5)
            if health.get('max_context') != 65536 or not health.get('loaded'):
                raise RuntimeError('existing service is not the 64K one-slot load')
            state['reused_loaded'] = True
        else:
            plan = subprocess.run(common + ['--plan'], env=env, capture_output=True, text=True, timeout=120)
            (out / 'plan.json').write_text(plan.stdout)
            if plan.returncode or not json.loads(plan.stdout).get('ok'):
                raise RuntimeError('64K launch plan refused')
            if (download := json.loads(plan.stdout)['plan']['download']).get('gb') != 0:
                raise RuntimeError('64K plan requires a download')
            event('restart', 'begin')
            if state['gpu_before_mib'].get(0, 0) > 1024:
                old_health = request('/health', timeout=5)
                if old_health.get('model') != 'qwen3.8-flash-next-unsloth-ud-q4_k_xl':
                    raise RuntimeError('GPU0 holds a different model')
                old_context = old_health.get('max_context')
                stopped = subprocess.run([str(CONTROL), 'launch', '--stop', '--output', 'json'],
                                         env=env, capture_output=True, text=True, timeout=120)
                (out / 'stop_stdout.json').write_text(stopped.stdout)
                if stopped.returncode:
                    raise RuntimeError('existing Strata service did not stop cleanly')
            stopped_existing = True
            launch = subprocess.run(common + ['--no-tui'], env=env,
                                    capture_output=True, text=True, timeout=1500)
            (out / 'launch_stdout.json').write_text(launch.stdout)
            (out / 'launch_stderr.txt').write_text(launch.stderr)
            event('restart', 'end', {'launch_exit': launch.returncode})
            if launch.returncode:
                raise RuntimeError(f'64K Strata launch failed: {launch.stderr[-400:]}')
        health = request('/health', timeout=5)
        if (not health.get('loaded') or health.get('max_context') != 65536
                or health.get('model') != 'qwen3.8-flash-next-unsloth-ud-q4_k_xl'):
            raise RuntimeError('64K health mismatch')
        state['health'] = health
        new_healthy = True
        state['host_loaded'] = memory()
        state['gpu_loaded_mib'] = gpu()
        for device in map(int, args.gpu_set.split(',')):
            if state['gpu_loaded_mib'].get(device, 0) < 512:
                raise RuntimeError(f'GPU{device} requested but has no useful allocation')
        if state['host_loaded']['MemAvailable_kib'] < 4 * 1048576:
            raise RuntimeError('host memory below 4 GiB after launch')
        messages = []
        line_start = 0
        for target, count in zip(TARGETS, LINES):
            prompt = (('The private code word is ORCHID. Remember it.\n' if not messages else '')
                      + filler(line_start, count)
                      + '\nStart your answer with ORCHID, then write a numbered list of 200 short observations about a garden. Continue until stopped.')
            line_start += count
            messages.append({'role': 'user', 'content': prompt})
            before = {'memory': memory(), 'gpu_mib': gpu(), 'block': block()}
            event(f'depth_{target}', 'begin', {'lines_total': line_start})
            start = time.monotonic()
            response = request('/v1/chat/completions',
                               {'model': 'strata', 'messages': messages, 'max_tokens': 256,
                                'temperature': 0}, timeout=1800)
            wall = round(time.monotonic() - start, 3)
            event(f'depth_{target}', 'end',
                  {'usage': response.get('usage'), 'timings': response.get('timings')})
            save(out / f'depth_{target}_response.json', response)
            choice = (response.get('choices') or [{}])[0]
            answer = (choice.get('message') or {}).get('content') or ''
            result = {'target_occupied_tokens': target, 'lines_total': line_start,
                      'prompt_tokens': (response.get('usage') or {}).get('prompt_tokens'),
                      'completion_tokens': (response.get('usage') or {}).get('completion_tokens'),
                      'wall_seconds': wall, 'timings': response.get('timings'),
                      'code_recalled': answer.strip().upper().startswith('ORCHID'),
                      'finish_reason': choice.get('finish_reason'),
                      'before': before, 'after': {'memory': memory(), 'gpu_mib': gpu(), 'block': block()}}
            state['cases'].append(result)
            messages.append({'role': 'assistant', 'content': answer})
            save(out / 'checkpoint.json', state)
            if result['after']['memory']['MemAvailable_kib'] < 4 * 1048576:
                raise RuntimeError(f'host memory below 4 GiB at {target}')
            if result['prompt_tokens'] and result['prompt_tokens'] >= 65536:
                raise RuntimeError(f'prompt exceeded context cap at {target}')
        state['status'] = 'passed'
    except BaseException as exc:
        state['status'] = 'failed'
        state['error'] = f'{type(exc).__name__}: {exc}'
        if stopped_existing and not new_healthy:
            try:
                subprocess.run([str(CONTROL), 'launch', '--stop', '--output', 'json'],
                               env=env, capture_output=True, text=True, timeout=120)
                old = common.copy()
                old[old.index('--gpu') + 1] = '0'
                old[old.index('--set') + 1] = 'resident-budget-gib=8'
                if old_context == 32768:
                    old[old.index('--context') + 1] = '32768'
                    old[old.index('--parallel') + 1] = '2'
                for removed in ('peer-device=1', 'kv-resident=32768'):
                    if removed in old:
                        i = old.index(removed)
                        del old[i - 1:i + 1]
                restored = subprocess.run(old + ['--no-tui'], env=env,
                                          capture_output=True, text=True, timeout=1500)
                state['rollback_exit'] = restored.returncode
                (out / 'rollback_stdout.json').write_text(restored.stdout)
                (out / 'rollback_stderr.txt').write_text(restored.stderr)
            except Exception as rollback_error:
                state['rollback_error'] = f'{type(rollback_error).__name__}: {rollback_error}'
    finally:
        engine_log = Path.home() / '.local/state/strata/launch/ud-q4_k_xl-64k.engine.log'
        if engine_log.is_file():
            shutil.copy2(engine_log, out / 'engine.log')
            state['engine_log'] = str(out / 'engine.log')
        state['host_final'] = memory()
        state['gpu_final_mib'] = gpu()
        state['finished_at'] = stamp()
        save(out / 'terminal.json', state)
        print(json.dumps({'status': state['status'], 'error': state.get('error'),
                          'receipt': str(out / 'terminal.json')}), flush=True)
    return 0 if state['status'] == 'passed' else 1

if __name__ == '__main__':
    raise SystemExit(main())
