#!/usr/bin/env python3
"""Fixed 50K prompt Strata speed experiment; leave final service loaded."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_strata_q4_smoke import CONTROL, DATA, MODEL, PACK, block, gpu, memory, save, stamp

COMPONENTS = Path('/data/bench-staging/strata-v0.2.10/components-cuda12')

PORT = 18144
ENGINE_LOG = Path.home() / '.local/state/strata/launch/ud-q4_k_xl-128k.engine.log'
ARMS = [('int8_a', 'int8', 12, False), ('k8v4_a', 'k8v4', 12, False),
        ('int8_b', 'int8', 12, False), ('k8v4_b', 'k8v4', 12, False),
        ('k8v4_ram16', 'k8v4', 16, False), ('k8v4_mtp', 'k8v4', 12, True)]

def prompt_fixture(out):
    path = out / 'fixed_50k_chat.json'
    if path.exists():
        return json.loads(path.read_text()), hashlib.sha256(path.read_bytes()).hexdigest()
    content = ('The private code word is ORCHID. Remember it.\n' +
               '\n'.join(f'Reference line {i:05d}: the ordinary ledger remains unchanged.' for i in range(3100)) +
               '\nStart with ORCHID, then give a numbered list of detailed observations about a garden. '
               'Keep writing until the response limit. /no_think')
    messages = [{'role': 'user', 'content': content}]
    path.write_text(json.dumps(messages, ensure_ascii=False, indent=2) + '\n')
    return messages, hashlib.sha256(path.read_bytes()).hexdigest()

def health():
    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=10) as r:
        return json.load(r)

def stream_request(messages, max_tokens):
    body = json.dumps({'model': 'strata', 'messages': messages, 'max_tokens': max_tokens,
                       'temperature': 0, 'stream': True,
                       'stream_options': {'include_usage': True}}).encode()
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}/v1/chat/completions', body,
                                 {'Content-Type': 'application/json'})
    t0 = time.monotonic()
    first = None
    chunks = 0
    usage = None
    finish = None
    chars = 0
    with urllib.request.urlopen(req, timeout=3600) as r:
        for raw in r:
            if not raw.startswith(b'data: '):
                continue
            data = raw[6:].strip()
            if data == b'[DONE]':
                break
            try:
                item = json.loads(data)
            except json.JSONDecodeError:
                continue
            if item.get('usage'):
                usage = item['usage']
            for choice in item.get('choices') or []:
                delta = choice.get('delta') or {}
                token_text = (delta.get('content') or '') + (delta.get('reasoning_content') or '')
                if token_text:
                    first = first or time.monotonic()
                    chunks += 1
                    chars += len(token_text)
                finish = choice.get('finish_reason') or finish
    end = time.monotonic()
    return {'wall_seconds': round(end-t0, 3),
            'first_content_seconds': round(first-t0, 3) if first else None,
            'post_first_seconds': round(end-first, 3) if first else None,
            'content_chunks': chunks, 'content_chars': chars, 'usage': usage,
            'finish_reason': finish}

def log_metrics(text):
    lines = text.splitlines()
    prompt = next((line for line in reversed(lines) if 'strata serve: prompt ' in line), None)
    cache = next((line for line in reversed(lines) if 'decode expert cache hit rate:' in line), None)
    slots = next((line for line in reversed(lines) if 'strata generate: expert cache ' in line and 'slots' in line), None)
    def number(pattern, line, cast=float):
        match = re.search(pattern, line or '')
        return cast(match.group(1)) if match else None
    return {'prompt_line': prompt, 'cache_line': cache, 'slots_line': slots,
            'prompt_tokens': number(r'prompt (\d+) tokens', prompt, int),
            'reused_tokens': number(r'= (\d+) reused', prompt, int),
            'prefill_ms': number(r'in (\d+) ms \(', prompt, int),
            'decode_tps': number(r'generated in \d+ ms \(([\d.]+) tok/s\)', prompt),
            'generated_tokens': number(r', (\d+) generated in', prompt, int),
            'cache_hit_percent': number(r'hit rate: ([\d.]+)%', cache),
            'cache_hits': number(r'\((\d+) hits', cache, int),
            'cache_lookups': number(r'/ (\d+) lookups', cache, int),
            'expert_cache_slots': number(r'expert cache (\d+) slots', slots, int)}

def run_arm(out, name, kv, resident, mtp, messages):
    arm_dir = out / name
    arm_dir.mkdir(exist_ok=True)
    env = dict(os.environ, STRATA_COMPONENTS_DIR=str(COMPONENTS), CUDA_DEVICE_ORDER='PCI_BUS_ID')
    common = [str(CONTROL), 'launch', '--family', 'unsloth', '--model', 'ud-q4_k_xl',
              '--model-path', str(MODEL), '--data-dir', str(DATA), '--backend', 'nvidia',
              '--context', '131072', '--kv', kv, '--vision', 'off', '--parallel', '1',
              '--mtp', 'on' if mtp else 'off', '--drafting', 'mtp' if mtp else 'off',
              '--set', f'resident-budget-gib={resident}', '--set', 'vram-reserve-mib=768',
              '--tune', 'skip', '--port', str(PORT), '--access', 'local', '--no-api-key',
              '--yes', '--output', 'json', '--gpu', '0']
    state = {'arm': name, 'kv': kv, 'resident_budget_gib': resident, 'mtp': mtp,
             'started_at': stamp(), 'status': 'running', 'memory_before': memory(),
             'gpu_before_mib': gpu()}
    save(arm_dir / 'terminal.json', state)
    try:
        plan = subprocess.run(common + ['--plan'], env=env, capture_output=True, text=True, timeout=120)
        (arm_dir / 'plan.json').write_text(plan.stdout)
        parsed = json.loads(plan.stdout)
        if plan.returncode or not parsed.get('ok'):
            raise RuntimeError('launch plan failed')
        download_gb = parsed['plan']['download']['gb']
        if download_gb and not (mtp and download_gb <= 6 and shutil.disk_usage('/data').free > 12 * 1024**3):
            raise RuntimeError('launch plan wants an unexpected or unsafe download')
        if memory()['MemAvailable_kib'] < 8 * 1048576:
            raise RuntimeError('host has less than 8 GiB available before launch')
        stop = subprocess.run([str(CONTROL), 'launch', '--stop', '--output', 'json'],
                              env=env, capture_output=True, text=True, timeout=180)
        (arm_dir / 'stop.json').write_text(stop.stdout)
        if stop.returncode:
            raise RuntimeError('existing load did not stop')
        launch_start = time.monotonic()
        launch = subprocess.run(common + ['--no-tui'], env=env,
                                capture_output=True, text=True, timeout=1800)
        state['load_seconds'] = round(time.monotonic()-launch_start, 3)
        (arm_dir / 'launch.json').write_text(launch.stdout)
        (arm_dir / 'launch_stderr.txt').write_text(launch.stderr)
        if launch.returncode or not health().get('loaded'):
            raise RuntimeError('launch unhealthy: ' + launch.stderr[-300:])
        if mtp:
            live_cfg = json.loads((Path.home() / '.local/state/strata/launch/ud-q4_k_xl-128k.json').read_text())
            live_args = live_cfg.get('args') or []
            if '--mtp' not in live_args or not Path(live_args[live_args.index('--mtp') + 1], 'experts.bin').is_file():
                raise RuntimeError('MTP requested but the live engine has no verified draft runtime path')
        state['memory_loaded'] = memory()
        state['gpu_loaded_mib'] = gpu()
        if state['memory_loaded']['MemAvailable_kib'] < 3 * 1048576:
            raise RuntimeError('host has less than 3 GiB available after launch')
        before_block = block()
        log_offset = ENGINE_LOG.stat().st_size if ENGINE_LOG.exists() else 0
        state['request_started_at'] = stamp()
        save(arm_dir / 'terminal.json', state)
        state['stream'] = stream_request(messages, 768)
        state['request_finished_at'] = stamp()
        after_block = block()
        state['nvme_read_bytes'] = max(0, after_block['nvme']['read_bytes']-before_block['nvme']['read_bytes'])
        state['block_before'] = before_block
        state['block_after'] = after_block
        log_text = ENGINE_LOG.read_text(errors='replace') if ENGINE_LOG.exists() else ''
        (arm_dir / 'engine_request.log').write_text(log_text[log_offset:])
        state['engine'] = log_metrics(log_text[log_offset:])
        state['memory_after'] = memory()
        state['gpu_after_mib'] = gpu()
        state['status'] = 'passed'
    except BaseException as exc:
        state['status'] = 'failed'
        state['error'] = f'{type(exc).__name__}: {exc}'
    state['finished_at'] = stamp()
    save(arm_dir / 'terminal.json', state)
    return state

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--only-arm', choices=[a[0] for a in ARMS])
    args = ap.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    messages, digest = prompt_fixture(out)
    manifest = {'status': 'running', 'started_at': stamp(), 'fixture_sha256': digest,
                'max_tokens': 768, 'context_cap': 131072, 'arms': [], 'end_state': 'freeze'}
    save(out / 'sequence.json', manifest)
    if not (PACK / 'index.txt').exists():
        raise RuntimeError('pack missing')
    selected = [a for a in ARMS if not args.only_arm or a[0] == args.only_arm]
    for name, kv, resident, mtp in selected:
        result = run_arm(out, name, kv, resident, mtp, messages)
        manifest['arms'].append({'name': name, 'status': result['status'],
                                 'error': result.get('error')})
        save(out / 'sequence.json', manifest)
        print(json.dumps({'arm': name, 'status': result['status'], 'error': result.get('error')}), flush=True)
        if result['status'] != 'passed':
            break
    manifest['status'] = 'passed' if len(manifest['arms']) == len(selected) and all(a['status'] == 'passed' for a in manifest['arms']) else 'failed'
    manifest['finished_at'] = stamp()
    save(out / 'sequence.json', manifest)
    return 0 if manifest['status'] == 'passed' else 1

if __name__ == '__main__':
    raise SystemExit(main())
