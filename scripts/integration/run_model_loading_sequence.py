#!/usr/bin/env python3
"""Run a guarded, resumable sequence of experimental model-loading cases.

Invoke on the rig through Manager's ``rigctl run-start``.  GPU cases normally acquire
their own benchmark lease. Frozen-service restarts require an existing persistent
claim and use restart_loaded because a live service is busy without a lease.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from hardware_inventory import scan_cards, require_ids

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


def normalize_manifest(source):
    """Expand schema 2 shared defaults into the existing stage contract."""
    if source.get('schema') == 1:
        return source
    if source.get('schema') != 2 or not isinstance(source.get('defaults'), dict) or not isinstance(source.get('cases'), list):
        raise ValueError('expected schema 1 stages or schema 2 defaults and cases')
    defaults = source['defaults']
    stages = []
    for case in source['cases']:
        if not isinstance(case, dict):
            raise ValueError('each case must be an object')
        stage = dict(defaults)
        stage.update(case)
        if stage.get('gpus') and 'freeze' not in stage:
            stage['freeze'] = True
        stages.append(stage)
    return {'schema': 1, 'stages': stages}


def write_comparison(folder, source, manifest, summary):
    """One index for all cases, backed by the immutable stage and trace receipts."""
    cases = []
    for stage in manifest['stages']:
        name = stage['id']
        receipt = folder / f'{name}.json'
        record = json.loads(receipt.read_text()) if receipt.exists() else {}
        trace_path = Path(record['trace_dir']) if record.get('trace_dir') else None
        trace_terminal = trace_path / 'terminal.json' if trace_path else None
        trace = json.loads(trace_terminal.read_text()) if trace_terminal and trace_terminal.exists() else None
        start, finish = record.get('started_at'), record.get('finished_at')
        elapsed = (datetime.fromisoformat(finish) - datetime.fromisoformat(start)).total_seconds() if start and finish else None
        cases.append({'id': name, 'label': stage.get('label'), 'hypothesis': stage.get('hypothesis'),
                      'baseline': stage.get('baseline'), 'status': summary['stages'].get(name, 'pending'),
                      'gpus': stage.get('gpus', []), 'placement': stage.get('placement'),
                      'stage_seconds': elapsed, 'receipt': str(receipt) if receipt.exists() else None,
                      'trace_dir': str(trace_path) if trace_path else None,
                      'trace': trace})
    atomic_json(folder / 'comparison.json',
                {'schema': 1, 'run_id': summary['run_id'], 'manifest_sha256': summary['manifest_sha256'],
                 'series_name': source.get('name'), 'updated_at': stamp(),
                 'status': summary.get('status', 'running'), 'cases': cases})


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
            if (not isinstance(stage.get('gpus', []), list)
                    or any(type(x) is not int or x < 0 for x in stage.get('gpus', []))
                    or len(set(stage.get('gpus', []))) != len(stage.get('gpus', []))):
                raise ValueError(f'{name}: gpus must be distinct nonnegative GPU IDs')
            if any(not isinstance(stage.get(flag, False), bool) for flag in ('freeze', 'reuse_loaded', 'restart_loaded', 'trace', 'continue_on_failure')):
                raise ValueError(f'{name}: freeze, reuse_loaded and trace must be booleans')
            if stage.get('reuse_loaded') and stage.get('restart_loaded'):
                raise ValueError(f'{name}: reuse_loaded and restart_loaded are exclusive')
            if stage.get('restart_loaded') and not stage.get('freeze'):
                raise ValueError(f'{name}: restart_loaded requires freeze')
            if stage.get('restart_loaded') and '--restart-loaded' not in stage['command']:
                raise ValueError(f'{name}: restart_loaded stage must pass --restart-loaded')
            if stage.get('reuse_loaded') and not stage.get('freeze'):
                raise ValueError(f'{name}: reuse_loaded requires freeze')
            if stage.get('reuse_loaded') and '--reuse-loaded' not in stage['command']:
                raise ValueError(f'{name}: reuse_loaded stage must pass --reuse-loaded to its command')
            if 'placement' in stage:
                placement = stage['placement']
                local_root = ROOT if ROOT.is_dir() else Path(__file__).resolve().parents[2]
                if (not isinstance(placement, str) or Path(placement).is_absolute()
                        or not (local_root / placement).is_file()):
                    raise ValueError(f'{name}: placement must be an existing repo-relative JSON path')
                if not isinstance(json.loads((local_root / placement).read_text()), dict):
                    raise ValueError(f'{name}: placement must contain a JSON object')
            env = stage.get('env', {})
            if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
                raise ValueError(f'{name}: env must be a string map')
            if 'max_host_drop_gb' in stage and (not isinstance(stage['max_host_drop_gb'], (int, float))
                                                or stage['max_host_drop_gb'] <= 0):
                raise ValueError(f'{name}: max_host_drop_gb must be positive')


def lease(action, *args):
    result = subprocess.run(['bash', str(LEASE), action, *map(str, args)], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'lease {action} failed: {(result.stderr or result.stdout).strip()[-500:]}')
    return result.stdout.strip()


def manager(*args):
    remote = shlex.join(['python3', '/home/bryan/llm-gateway/tools/rigctl.py', *map(str, args)])
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'pi', remote],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"Manager {' '.join(map(str, args[:2]))} failed: "
                           f"{(result.stderr or result.stdout).strip()[-500:]}")
    return json.loads(result.stdout)


def session_claim(name, gpu_ids, purpose, create):
    claims = manager('claims')['claims']
    match = next((item for item in claims if item['name'] == name), None)
    if create and not match:
        manager('claim', name, '--gpus', ','.join(map(str, gpu_ids)), '--owner', name,
                '--purpose', purpose, '--note', 'benchmark sequence; persists through frozen model state')
        claims = manager('claims')['claims']
        match = next((item for item in claims if item['name'] == name), None)
    elif create and match and set(match['gpu_ids']) != set(gpu_ids):
        if not set(match['gpu_ids']).issubset(gpu_ids):
            raise RuntimeError(f'session claim {name} cannot shrink or switch GPUs')
        manager('extend-claim', name, '--gpus', ','.join(map(str, gpu_ids)),
                '--owner', match.get('owner') or name)
        claims = manager('claims')['claims']
        match = next((item for item in claims if item['name'] == name), None)
    if not match:
        raise RuntimeError(f'session claim {name} missing')
    if create and set(match['gpu_ids']) != set(gpu_ids):
        raise RuntimeError(f'session claim {name} GPU set does not match request')
    if match.get('ttl_s') or match.get('expires_at'):
        raise RuntimeError(f'session claim {name} has a TTL; use a persistent claim')
    return match


def renew_lease(lease_id, owner):
    # The shared shell wrapper intentionally ignores renewal failures for old
    # lanes. This campaign must stop if the Manager cannot renew its claim.
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'pi',
                             'python3', '/home/bryan/llm-gateway/tools/rigctl.py',
                             'renew', lease_id, '--owner', owner, '--ttl', '600'],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'lease renewal failed: {(result.stderr or result.stdout).strip()[-500:]}')


def expand_stage(stage, run_id):
    expanded = dict(stage)
    for key in ('command', 'outputs', 'absent'):
        if key in stage:
            expanded[key] = [value.replace('{run_id}', run_id) for value in stage[key]]
    return expanded


def run_stage(stage, folder, run_id, claim=None):
    name = stage['id']
    floor = int(stage.get('mem_floor_gib', 4)) * 1048576
    record = {'id': name, 'status': 'running', 'started_at': stamp(), 'command': stage['command'],
              'gpus': stage.get('gpus', []), 'timeout_s': stage['timeout_s'],
              'env_keys': sorted(stage.get('env', {})), 'claim': claim,
              'end_state_requested': 'freeze' if stage.get('freeze') else 'release',
              'trace': stage.get('trace', False)}
    receipt = folder / f'{name}.json'
    atomic_json(receipt, record)
    lease_id = ''
    proc = None
    try:
        host_before = mem_available_kib()
        record['host_before_available_kib'] = host_before
        record['host_min_available_kib'] = host_before
        max_drop_kib = int(stage.get('max_host_drop_gb', 0) * 1_000_000_000 / 1024)
        if host_before < floor:
            raise RuntimeError('host memory below floor before start')
        gpus = stage.get('gpus', [])
        if gpus and (stage.get('reuse_loaded') or stage.get('restart_loaded')) and not claim:
            raise RuntimeError('reuse_loaded requires a persistent session claim')
        if gpus and not (stage.get('reuse_loaded') or stage.get('restart_loaded')):
            lease_id = lease('acquire', ','.join(map(str, gpus)), run_id, run_id, name, claim or '')
            if not lease_id:  # harness_lease.sh permits offline runs; this sequence does not.
                raise RuntimeError('Manager unreachable: lease ID missing')
        command = stage['command']
        if stage.get('trace'):
            attempt = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            trace_dir = folder / f'{name}_tier_trace_{attempt}'
            prefix = ['python3', str(ROOT / 'scripts/integration/tier_trace.py'), 'run',
                      '--output', str(trace_dir)]
            if stage.get('placement'):
                prefix += ['--placement', str(ROOT / stage['placement'])]
            command = [*prefix, '--', *command]
            record['trace_dir'] = str(trace_dir)
        with (folder / f'{name}.log').open('w') as log:
            proc = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    env=dict(os.environ, **stage.get('env', {})), start_new_session=True)
            began = time.monotonic()
            next_renew = began + 120
            while proc.poll() is None:
                if time.monotonic() - began > stage['timeout_s']:
                    raise RuntimeError('stage timeout')
                if gpus:
                    available = mem_available_kib()
                    record['host_min_available_kib'] = min(record['host_min_available_kib'], available)
                    if available < floor:
                        raise RuntimeError('host memory fell below floor')
                    if max_drop_kib and host_before - available > max_drop_kib:
                        raise RuntimeError('host available-memory drop exceeded stage ceiling')
                if lease_id and time.monotonic() >= next_renew:
                    renew_lease(lease_id, run_id)
                    next_renew = time.monotonic() + 120
                time.sleep(2)
        record['exit_code'] = proc.returncode
        if proc.returncode:
            raise RuntimeError(f'exit {proc.returncode}; see {name}.log')
        if stage.get('trace') and not (trace_dir / 'terminal.json').is_file():
            raise RuntimeError('missing tier trace terminal receipt')
        for output in stage.get('outputs', []):
            if not Path(output).exists():
                raise RuntimeError(f'missing required output: {output}')
        for output in stage.get('absent', []):
            if Path(output).exists():
                raise RuntimeError(f'forbidden output exists: {output}')
        record['status'] = 'passed'
        if stage.get('freeze'):
            if not claim:
                raise RuntimeError('freeze requires a persistent session claim')
            record['frozen_claim'] = claim
    except BaseException as exc:
        record['status'] = 'failed'
        record['error'] = str(exc)
        if isinstance(exc, KeyboardInterrupt):
            record['interrupted'] = True
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
                if stage.get('freeze') and claim and record['status'] == 'passed':
                    manager('release', lease_id, '--owner', run_id, '--force')
                else:
                    manager('release', lease_id, '--owner', run_id)
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
    ap.add_argument('--through', help='stop successfully after this stage; later queue stages remain pending')
    ap.add_argument('--claim', help='use an existing persistent benchmark claim')
    ap.add_argument('--session-gpus', help='reserve all planned cards for this run, e.g. 0,1,2; claim persists after run')
    ap.add_argument('--session-purpose', default='model-loading benchmark', help='purpose shown to other sessions')
    args = ap.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        ap.error('unsafe run ID')
    session_gpus = None
    if args.session_gpus:
        try:
            session_gpus = sorted(set(int(g) for g in args.session_gpus.split(',')))
        except ValueError:
            ap.error('--session-gpus must be comma-separated GPU IDs')
        if not session_gpus or any(g < 0 for g in session_gpus):
            ap.error('--session-gpus must contain nonnegative GPU IDs')
    raw = args.manifest.read_bytes()
    source = json.loads(raw)
    manifest = normalize_manifest(source)
    validate(manifest)
    if args.through and args.through not in {stage['id'] for stage in manifest['stages']}:
        ap.error(f'unknown --through stage: {args.through}')
    digest = hashlib.sha256(raw).hexdigest()
    if args.check:
        print(json.dumps({'manifest_sha256': digest, 'stages': [
            {'id': s['id'], 'state': s['state'], 'reason': s.get('reason'), 'gpus': s.get('gpus', [])}
            for s in manifest['stages']]}, indent=2))
        return 0
    cards = scan_cards()
    requested = set(session_gpus or [])
    for stage in manifest['stages']:
        if stage['state'] == 'ready':
            requested.update(stage.get('gpus', []))
    require_ids(requested, cards)
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
    claim = args.claim or (args.run_id if session_gpus else None)
    if any(stage['state'] == 'ready' and stage.get('freeze') and stage.get('gpus') for stage in manifest['stages']) and not claim:
        raise SystemExit('frozen GPU stages require --claim or --session-gpus before execution')
    if claim:
        held = session_claim(claim, session_gpus or [], args.session_purpose, bool(session_gpus))
        for stage in manifest['stages']:
            if stage['state'] == 'ready' and not set(stage.get('gpus', [])).issubset(held['gpu_ids']):
                raise SystemExit(f"stage {stage['id']} uses GPUs outside session claim {claim}")
    summary = {'run_id': args.run_id, 'manifest_sha256': digest, 'started_at': stamp(),
               'session_claim': claim, 'reserved_gpus': held['gpu_ids'] if claim else [], 'stages': {}}
    terminal = folder / 'terminal.json'
    failures = []
    write_comparison(folder, source, manifest, summary)
    for raw_stage in manifest['stages']:
        stage = expand_stage(raw_stage, args.run_id)
        name = stage['id']
        existing = folder / f'{name}.json'
        if (existing.exists() and json.loads(existing.read_text()).get('status') == 'passed'
                and all(Path(p).exists() for p in stage.get('outputs', []))
                and all(not Path(p).exists() for p in stage.get('absent', []))):
            summary['stages'][name] = 'reused'
            write_comparison(folder, source, manifest, summary)
            if name == args.through:
                summary['status'] = 'completed_to_stage'
                break
            continue
        if stage['state'] == 'blocked':
            summary['stages'][name] = 'blocked'
            summary['status'] = 'blocked'
            summary['reason'] = stage['reason']
            write_comparison(folder, source, manifest, summary)
            break
        result = run_stage(stage, folder, args.run_id, claim)
        summary['stages'][name] = result['status']
        write_comparison(folder, source, manifest, summary)
        if result.get('interrupted'):
            summary['status'] = 'interrupted'
            summary['reason'] = result.get('error')
            break
        if result['status'] != 'passed':
            failures.append(name)
            summary['failures'] = failures
            summary['status'] = 'failed'
            summary['reason'] = result.get('error') or result.get('release_error')
            if stage.get('continue_on_failure'):
                continue
            break
        if name == args.through:
            summary['status'] = 'completed_to_stage'
            break
    else:
        summary['status'] = 'completed_with_failures' if failures else 'passed'
    summary['finished_at'] = stamp()
    atomic_json(terminal, summary)
    write_comparison(folder, source, manifest, summary)
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary['status'] in ('passed', 'completed_to_stage') else 1


if __name__ == '__main__':
    raise SystemExit(main())
