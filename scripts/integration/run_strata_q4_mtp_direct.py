#!/usr/bin/env python3
"""Measure a fixed 50K Strata prompt with a verified local MTP runtime."""
import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

from run_strata_q4_fixed50k_speed import (
    CONTROL, COMPONENTS, ENGINE_LOG, block, gpu, health, log_metrics, memory,
    prompt_fixture, save, stamp, stream_request,
)

RT = Path('/data/model-hotset/qwen3.8-flash-next-ud-q4_k_xl/runtime/strata-ud-q4_k_xl/mtp/rt')
BASE = Path.home() / '.local/state/strata/launch/ud-q4_k_xl-128k.json'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    messages, digest = prompt_fixture(out)
    state = {'status': 'running', 'started_at': stamp(), 'fixture_sha256': digest,
             'kv': 'k8v4', 'resident_budget_gib': 12, 'mtp': True,
             'context_cap': 131072, 'max_tokens': 768}
    save(out / 'terminal.json', state)
    env = dict(os.environ, STRATA_COMPONENTS_DIR=str(COMPONENTS), CUDA_DEVICE_ORDER='PCI_BUS_ID')
    try:
        for name in ('experts.bin', 'dense.bin', 'dense.txt'):
            if not (RT / name).is_file():
                raise RuntimeError(f'MTP runtime missing {name}')
        config = json.loads(BASE.read_text())
        flags = list(config['args'])
        if flags[flags.index('--kv') + 1] != 'k8v4' or '--mtp' in flags:
            raise RuntimeError('base config is not the expected K8V4 no-MTP control')
        flags += ['--mtp', str(RT), '--spec-min-p', '0.5']
        config['args'] = flags
        config['args_written'] = flags.copy()
        config['mtp'] = True
        config['drafting'] = 'mtp'
        config['log'] = str(out / 'engine.log')
        config_path = out / 'mtp_config.json'
        save(config_path, config)
        cmd = [str(CONTROL), 'serve', '--profile', str(config_path), '--host', '127.0.0.1',
               '--port', '18144', '--parallel', '1']
        plan = subprocess.run(cmd + ['--plan', '--output', 'json'], env=env,
                              capture_output=True, text=True, timeout=120)
        (out / 'serve_plan.json').write_text(plan.stdout)
        (out / 'serve_plan_stderr.txt').write_text(plan.stderr)
        if plan.returncode or not json.loads(plan.stdout).get('ok'):
            raise RuntimeError('direct MTP serve plan failed: ' + plan.stderr[-300:])
        stop = subprocess.run([str(CONTROL), 'launch', '--stop', '--output', 'json'],
                              env=env, capture_output=True, text=True, timeout=180)
        (out / 'stop.json').write_text(stop.stdout)
        if stop.returncode:
            raise RuntimeError('previous Strata load did not stop')
        launch_start = time.monotonic()
        with (out / 'serve_stdout.log').open('w') as log:
            proc = subprocess.Popen(cmd + ['--ready-file', str(out / 'ready.json')],
                                    env=env, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True, stdin=subprocess.DEVNULL)
        state['serve_pid'] = proc.pid
        for _ in range(180):
            if proc.poll() is not None:
                raise RuntimeError(f'direct MTP serve exited {proc.returncode}')
            try:
                if health().get('loaded'):
                    break
            except Exception:
                pass
            time.sleep(2)
        else:
            raise RuntimeError('direct MTP serve did not become healthy')
        state['load_seconds'] = round(time.monotonic()-launch_start, 3)
        live = subprocess.run(['ps', '-eo', 'pid,args'], capture_output=True, text=True, check=True).stdout
        engine_lines = [line for line in live.splitlines() if 'strata --serve' in line and '--mtp ' + str(RT) in line]
        if len(engine_lines) != 1:
            raise RuntimeError('exactly one live engine with the MTP runtime path was not found')
        state['engine_process'] = engine_lines[0].strip()
        state['memory_loaded'] = memory()
        state['gpu_loaded_mib'] = gpu()
        if state['memory_loaded']['MemAvailable_kib'] < 3*1048576:
            raise RuntimeError('less than 3 GiB host memory available after MTP load')
        before = block()
        state['request_started_at'] = stamp()
        save(out / 'terminal.json', state)
        state['stream'] = stream_request(messages, 768)
        state['request_finished_at'] = stamp()
        after = block()
        state['nvme_read_bytes'] = max(0, after['nvme']['read_bytes']-before['nvme']['read_bytes'])
        state['block_before'] = before
        state['block_after'] = after
        state['engine'] = log_metrics((out / 'engine.log').read_text(errors='replace'))
        state['memory_after'] = memory()
        state['gpu_after_mib'] = gpu()
        state['status'] = 'passed'
    except BaseException as exc:
        state['status'] = 'failed'
        state['error'] = f'{type(exc).__name__}: {exc}'
    state['finished_at'] = stamp()
    save(out / 'terminal.json', state)
    print(json.dumps({'status': state['status'], 'error': state.get('error')}), flush=True)
    return 0 if state['status'] == 'passed' else 1

if __name__ == '__main__':
    raise SystemExit(main())
