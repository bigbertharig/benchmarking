from __future__ import annotations

import json
import re
from pathlib import Path

source = Path('/mnt/shared/experiments/kv-expert-chat-20261107')
labels = [
    'matched_local_A1_short', 'matched_local_B_short', 'matched_local_A2_short',
    'matched_local_B_depth', 'matched_local_A_depth',
]
expected_first = {
    'worker4': ' Tokyo',
    'worker5': ' Berlin',
    'large_pair45': ' Ottawa',
}
summary = {}
for label in labels:
    log_path = source / f'{label}.log'
    if not log_path.exists():
        continue
    log = log_path.read_text(errors='replace')
    phases = {
        name: {
            'chats': int(chats),
            'tokens_each': int(tokens),
            'seconds': float(seconds),
            'aggregate_tps': float(rate),
            'ok': ok == '1',
        }
        for name, chats, tokens, seconds, rate, ok in re.findall(
            r'^PARALLEL phase=(\S+) chats=(\d+) tokens_each=(\d+) '
            r'seconds=([\d.]+) aggregate_tps=([\d.]+) ok=(\d+)$',
            log, re.M,
        )
    }
    peak_mib: dict[str, int] = {}
    for line in (source / f'{label}.gpu.csv').read_text(errors='replace').splitlines():
        match = re.search(r',\s*(\d+),\s*(\d+) MiB,', line)
        if match:
            card, used = match.groups()
            peak_mib[card] = max(peak_mib.get(card, 0), int(used))
    first = dict(re.findall(r'^FIRST name=(\S+) token=\d+ text=(.*)$', log, re.M))
    fills = [
        (name, int(target))
        for name, target in re.findall(r'^FILL_DONE name=(\S+) target=(\d+)', log, re.M)
    ]
    benches = [
        (name, phase, int(used))
        for name, phase, used in re.findall(
            r'^BENCH name=(\S+) phase=(\S+) used=(\d+)', log, re.M,
        )
    ]
    model_buffers = {
        card: float(mib)
        for card, mib in re.findall(
            r'^load_tensors:\s+CUDA(\d+) model buffer size =\s+([\d.]+) MiB$',
            log, re.M,
        )
    }
    exit_path = source / f'{label}.exit'
    code = exit_path.read_text().strip() if exit_path.exists() else None
    depth = label.endswith('_depth')
    expected_phases = {'depth10', 'depth90'} if depth else {'two_workers', 'two_workers_plus_pair'}
    summary[label] = {
        'exit': code,
        'valid': code == '0' and log.count('MODEL_READY one weight load') == 1
        and first == expected_first and set(phases) == expected_phases
        and all(p['ok'] for p in phases.values())
        and (not depth or (len(fills) == 6 and len(benches) == 6
            and all(used >= (29491 if name == 'large_pair45' else 7372)
                    for name, phase, used in benches if phase == 'depth90'))),
        'first_tokens': first,
        'phases': phases,
        'fills': fills,
        'benches': benches,
        'model_buffers_mib': model_buffers,
        'peak_gpu_mib': peak_mib,
        'graph_splits': sorted({int(x) for x in re.findall(r'graph: nodes = \d+, splits = (\d+)', log)}),
    }

control = summary.get('matched_local_A1_short', {}).get('model_buffers_mib', {})
for row in summary.values():
    buffers = row['model_buffers_mib']
    row['buffer_matched'] = set(buffers) == set(control) == {'0', '1', '2', '3', '4'} and all(
        abs(buffers[card] - control[card]) < 5 for card in control
    )
    row['valid'] = row['valid'] and row['buffer_matched']

path = source / 'matched_placement_20261107' / 'summary.json'
path.write_text(json.dumps(summary, indent=2) + '\n')
for label, data in summary.items():
    rates = ', '.join(f'{key}={value["aggregate_tps"]:.2f}' for key, value in data['phases'].items())
    print(f'{label}: exit={data["exit"]} valid={data["valid"]} {rates}')
