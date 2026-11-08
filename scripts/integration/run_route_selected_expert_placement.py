#!/usr/bin/env python3
"""Select a routed Q2 expert from an earlier trace and measure physical placements."""
import argparse
import collections
import csv
import json
import os
import subprocess
import time
from pathlib import Path

from run_strata_q4_smoke import block, gpu, memory, save, stamp

ROOT = Path('/mnt/shared/plans/shoulders/benchmarking')
TRACE = ROOT / 'results/runtime_experiments/model_loading_sequences/bigmoe-q2-route-trace-20261108/bigmoe_q2_route_trace_detail/route_trace.csv'
MODEL = Path('/data/model-hotset/qwen3.8-flash-next-q2_0/Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00001-of-00002.gguf')
GGUF_PY = Path('/data/bench-staging/strata-v0.2.10/install/third_party/llama.cpp/gguf-py')
SAMPLE = Path('/mnt/shared/experiments/route-expert-20261108')

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    state = {'status': 'running', 'started_at': stamp(), 'trace': str(TRACE),
             'model': str(MODEL), 'method': 'layer-0 top expert in first half of decode steps; real Q2 tensor sample and CUDA placement benchmark'}
    save(out / 'checkpoint.json', state)
    try:
        with TRACE.open(newline='') as f:
            rows = [r for r in csv.DictReader(x for x in f if not x.startswith('#'))
                    if int(r['phase']) == 1 and int(r['layer']) == 0]
        steps = sorted({int(r['step']) for r in rows})
        if len(steps) < 8: raise RuntimeError('too few routed decode steps')
        early = set(steps[:len(steps)//2])
        counts = collections.Counter(int(r['expert']) for r in rows if int(r['step']) in early)
        expert, hits = counts.most_common(1)[0]
        late = [int(r['expert']) for r in rows if int(r['step']) not in early]
        state['selection'] = {'layer': 0, 'expert': expert, 'early_hits': hits,
                              'late_coverage': round(sum(x == expert for x in late) / len(late), 4)}
        state['host_before'] = memory(); state['gpu_before_mib'] = gpu(); state['block_before'] = block()
        if state['host_before']['MemAvailable_kib'] < 8*1048576: raise RuntimeError('less than 8 GiB available')
        sample = SAMPLE / f'layer0_expert{expert}_two_workers'
        command = ['python3', str(ROOT / 'scripts/active/prepare_q38_tiered_expert_sample.py'),
                   '--gguf', str(MODEL), '--gguf-py', str(GGUF_PY),
                   '--output', str(sample), '--layer', '0', '--expert', str(expert), '--workers', '2']
        state['extract_command'] = command
        extract = subprocess.run(command, capture_output=True, text=True, timeout=600)
        (out/'extract_stdout.txt').write_text(extract.stdout)
        (out/'extract_stderr.txt').write_text(extract.stderr)
        if extract.returncode: raise RuntimeError(f'extract exit {extract.returncode}: {extract.stderr[-500:]}')
        state['sample'] = json.loads((sample/'sample.json').read_text())
        command = ['docker', 'run', '--rm', '--network', 'none', '--gpus', 'all',
                   '--user', f'{os.getuid()}:{os.getgid()}', '-e', 'WORKERS=2',
                   '-v', f'{ROOT}:/bench:ro', '-v', f'{sample}:/sample',
                   '--entrypoint', '/bin/bash', 'nvidia/cuda:12.9.2-devel-ubuntu24.04',
                   '/bench/scripts/active/run_q38_tiered_expert_probe.sh']
        state['benchmark_command'] = command
        start = time.monotonic()
        with (out/'benchmark_stdout.txt').open('w') as stdout, (out/'benchmark_stderr.txt').open('w') as stderr:
            result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=1800)
        state['benchmark_seconds'] = round(time.monotonic()-start, 3)
        state['benchmark_exit'] = result.returncode
        if result.returncode: raise RuntimeError(f'CUDA benchmark exited {result.returncode}')
        lines = [json.loads(x) for x in (out/'benchmark_stdout.txt').read_text().splitlines() if x.startswith('{')]
        if len(lines) != 6 or any('mode' not in x for x in lines):
            raise RuntimeError(f'expected six physical placement rows, got {len(lines)}')
        state['placements'] = lines
        state['status'] = 'passed'
    except BaseException as e:
        state['status'] = 'failed'; state['error'] = f'{type(e).__name__}: {e}'
    finally:
        state['finished_at'] = stamp(); state['host_final'] = memory(); state['gpu_final_mib'] = gpu(); state['block_final'] = block()
        save(out/'terminal.json', state)
        print(json.dumps({'status': state['status'], 'error': state.get('error'), 'receipt': str(out/'terminal.json')}), flush=True)
    return 0 if state['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
