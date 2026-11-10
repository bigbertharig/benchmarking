#!/usr/bin/env python3
"""Summarize matched two-chat admission logs after every campaign stage passes."""

from pathlib import Path
import json
import re

ROOT = Path('/mnt/shared/plans/shoulders/benchmarking')
RAW = Path('/mnt/shared/experiments/kv-matrix-20261107')
OUT = ROOT / 'results/runtime_experiments/model_loading_sequences/qwen35-two-admission-small-20261109'
DEPTHS = (16384, 32768, 50000)
PATHS = ('direct', 'ram', 'helper')


def fields(line):
    return dict(re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)=([^ ]+)', line))


summary = {'model': 'Qwen3.6-35B-A3B Q4_K_XL',
           'worker_kv': 'F16', 'worker_reservation': 262144,
           'generated_tokens_per_window': 512, 'paths': {}}
for placement in PATHS:
    label = f'qwen35_two_admission_{placement}_16k32k50k_20261109'
    assert (RAW / f'{label}.exit').read_text().strip() == '0', label
    by_depth = {str(depth): {'admission': {}, 'generation': {}, 'recall': {}}
                for depth in DEPTHS}
    for line in (RAW / f'{label}.log').read_text(errors='replace').splitlines():
        if line.startswith('TWO_ADMIT '):
            row = fields(line)
            depth = row.pop('depth')
            name = row.pop('name')
            by_depth[depth]['admission'][name] = {k: float(v) for k, v in row.items()
                                                  if k.endswith('_s')}
        elif line.startswith('GEN_METRIC phase=depth'):
            row = fields(line)
            match = re.fullmatch(r'depth(\d+)_(solo|during_second_admission|two_ready)',
                                 row['phase'])
            if match:
                depth, phase = match.groups()
                by_depth[depth]['generation'].setdefault(phase, {})[row['name']] = {
                    k: float(row[k]) for k in ('tps', 'seconds', 'first_ms', 'p50_ms', 'p95_ms')}
        elif line.startswith('RECALL_RESULT '):
            row = fields(line)
            depth = row['depth']
            by_depth[depth]['recall'][row['name']] = row['final_pass'] == '1'
    for depth, record in by_depth.items():
        assert set(record['admission']) == {'worker1', 'worker2'}, (placement, depth, record)
        assert set(record['generation']) == {'solo', 'during_second_admission', 'two_ready'}
        assert record['recall'] == {'worker1': True, 'worker2': True}
        record['first_ready_s'] = record['admission']['worker1']['stage_elapsed_s']
        record['both_ready_s'] = record['admission']['worker2']['stage_elapsed_s']
    peaks = {}
    for line in (RAW / f'{label}.gpu.csv').read_text(errors='replace').splitlines():
        parts = line.split(',')
        if len(parts) < 3:
            continue
        try:
            gpu = int(parts[1].strip())
            used_mib = int(parts[2].strip().split()[0])
        except (ValueError, IndexError):
            continue
        peaks[str(gpu)] = max(peaks.get(str(gpu), 0), used_mib)
    summary['paths'][placement] = {'depths': by_depth, 'sampled_gpu_peak_mib': peaks}

(OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(OUT / 'summary.json')
