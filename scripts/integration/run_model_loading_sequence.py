#!/usr/bin/env python3
"""Run a guarded, resumable sequence of experimental model-loading cases.

Invoke on the rig through Manager's ``rigctl run-start``.  GPU cases acquire
their own benchmark lease; a refusal or an unreachable Manager stops the queue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/mnt/shared/plans/shoulders/benchmarking')
LEASE = ROOT / 'scripts/integration/harness_lease.sh'
RESULTS = ROOT / 'results/runtime_experiments/model_loading_sequences'


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    os.replace(temp, path)


def mem_available_kib():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1])
    raise RuntimeError('MemAvailable missing')


def validate(manifest):
    if manifest.get('schema') != 1 or not isinstance(manifest.get('stages'), list):
        raise ValueError('expected schema 1 and stages list')
    seen = set()
    for stage in manifest['stages']:
        name = stage.get('id')
        if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_]*', name) or name in seen:
            raise ValueError(f'invalid or duplicate stage ID: {name}')
        seen.add(name)
        if stage.get('state') not in ('ready', 'blocked'):
            raise ValueError(f'{name}: state must be ready or blocked')
        if stage['state'] == 'blocked' and not stage.get('reason'):
            raise ValueError(f'{name}: blocked stage needs a reason')
        if stage['state'] == 'ready':
            cmd = stage.get('command')
            if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) and x for x in cmd):
                raise ValueError(f'{name}: command must be an argv list')
            if not isinstance(stage.get('timeout_s'), int) or stage['timeout_s'] < 1:
                raise ValueError(f'{name}: positive timeout_s required')
            if not isinstance(stage.get('gpus', []), list) or any(x not in range(6) for x in stage.get('gpus', [])):
                raise ValueError(f'{name}: gpus must be IDs 0..5')


def lease(action, *args):
    result = subprocess.run(['bash', str(LEASE), action, *map(str, args)], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'lease {action} failed: {(result.stderr or result.stdout).strip()[-500:]}')
    return result.stdout.strip()


def renew_lease(lease_id, owner):
    # The shared shell wrapper intentionally ignores renewal failures for old
    # lanes. This campaign must stop if the Manager cannot renew its claim.
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'pi',
                             'python3', '/home/bryan/llm-gateway/tools/rigctl.py',
                             'renew', lease_id, '--owner', owner, '--ttl', '600'],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'lease renewal failed: {(result.stderr or result.stdout).strip()[-500:]}')


def run_stage(stage, folder, run_id):
    name = stage['id']
    floor = int(stage.get('mem_floor_gib', 4)) * 1048576
    record = {'id': name, 'status': 'running', 'started_at': stamp(), 'command': stage['command'],
              'gpus': stage.get('gpus', []), 'timeout_s': stage['timeout_s']}
    receipt = folder / f'{name}.json'
    atomic_json(receipt, record)
    lease_id = ''
    proc = None
    try:
        if mem_available_kib() < floor:
            raise RuntimeError('host memory below floor before start')
        gpus = stage.get('gpus', [])
        if gpus:
            lease_id = lease('acquire', ','.join(map(str, gpus)), run_id, run_id, name)
            if not lease_id:  # harness_lease.sh permits offline runs; this sequence does not.
                raise RuntimeError('Manager unreachable: lease ID missing')
        with (folder / f'{name}.log').open('w') as log:
            proc = subprocess.Popen(stage['command'], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            began = time.monotonic()
            next_renew = began + 120
            while proc.poll() is None:
                if time.monotonic() - began > stage['timeout_s']:
                    raise RuntimeError('stage timeout')
                if gpus and mem_available_kib() < floor:
                    raise RuntimeError('host memory fell below floor')
                if lease_id and time.monotonic() >= next_renew:
                    renew_lease(lease_id, run_id)
                    next_renew = time.monotonic() + 120
                time.sleep(2)
        record['exit_code'] = proc.returncode
        if proc.returncode:
            raise RuntimeError(f'exit {proc.returncode}; see {name}.log')
        for output in stage.get('outputs', []):
            if not Path(output).exists():
                raise RuntimeError(f'missing required output: {output}')
        for output in stage.get('absent', []):
            if Path(output).exists():
                raise RuntimeError(f'forbidden output exists: {output}')
        record['status'] = 'passed'
    except BaseException as exc:
        record['status'] = 'failed'
        record['error'] = str(exc)
        if proc and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        record['exit_code'] = proc.returncode if proc else None
    finally:
        if lease_id:
            try:
                lease('release', lease_id, run_id)
            except Exception as exc:
                record['release_error'] = str(exc)
                record['status'] = 'failed'
        record['finished_at'] = stamp()
        atomic_json(receipt, record)
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('manifest', type=Path)
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--check', action='store_true', help='show the sequence without creating receipts')
    args = ap.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        ap.error('unsafe run ID')
    raw = args.manifest.read_bytes()
    manifest = json.loads(raw)
    validate(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    if args.check:
        print(json.dumps({'manifest_sha256': digest, 'stages': [
            {'id': s['id'], 'state': s['state'], 'reason': s.get('reason'), 'gpus': s.get('gpus', [])}
            for s in manifest['stages']]}, indent=2))
        return 0
    def stop(_signum, _frame):
        raise KeyboardInterrupt('Manager stopped the sequence')
    signal.signal(signal.SIGTERM, stop)
    folder = RESULTS / args.run_id
    folder.mkdir(parents=True, exist_ok=True)
    import fcntl
    lock = (folder / 'sequence.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(f'run ID {args.run_id} is already active')
    anchor = folder / 'manifest.json'
    if anchor.exists():
        if json.loads(anchor.read_text())['sha256'] != digest:
            raise SystemExit('manifest changed; use a fresh run ID')
    else:
        atomic_json(anchor, {'sha256': digest, 'manifest': str(args.manifest), 'created_at': stamp()})
    summary = {'run_id': args.run_id, 'manifest_sha256': digest, 'started_at': stamp(), 'stages': {}}
    terminal = folder / 'terminal.json'
    for stage in manifest['stages']:
        name = stage['id']
        existing = folder / f'{name}.json'
        if (existing.exists() and json.loads(existing.read_text()).get('status') == 'passed'
                and all(Path(p).exists() for p in stage.get('outputs', []))
                and all(not Path(p).exists() for p in stage.get('absent', []))):
            summary['stages'][name] = 'reused'
            continue
        if stage['state'] == 'blocked':
            summary['stages'][name] = 'blocked'
            summary['status'] = 'blocked'
            summary['reason'] = stage['reason']
            break
        result = run_stage(stage, folder, args.run_id)
        summary['stages'][name] = result['status']
        if result['status'] != 'passed':
            summary['status'] = 'failed'
            summary['reason'] = result.get('error') or result.get('release_error')
            break
    else:
        summary['status'] = 'passed'
    summary['finished_at'] = stamp()
    atomic_json(terminal, summary)
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
