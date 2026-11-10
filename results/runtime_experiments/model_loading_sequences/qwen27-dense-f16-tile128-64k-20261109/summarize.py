#!/usr/bin/env python3
"""Parse the matched one-worker dense and MoE F16 64-token replays."""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

repo = Path('/mnt/shared/plans/shoulders/benchmarking')
raw = Path('/mnt/shared/experiments/kv-matrix-20261107')
out = repo / 'results/runtime_experiments/model_loading_sequences/qwen27-dense-f16-tile128-64k-20261109'

def metrics(name: str) -> dict[str, dict]:
    lines = (raw / (name + '.log')).read_text().splitlines()
    result = {}
    for line in lines:
        if not line.startswith('GEN_METRIC phase=depth') or '_worker_solo ' not in line:
            continue
        fields = dict(re.findall(r'(\w+)=([^ ]+)', line))
        depth = re.search(r'depth(\d+)_worker_solo', fields['phase']).group(1)
        result[depth] = {key: float(fields[key]) for key in ('seconds', 'tps', 'first_ms', 'p50_ms', 'p95_ms')}
        result[depth]['tokens'] = int(fields['tokens'])
        result[depth]['used'] = int(fields['used'])
    assert set(result) == {'16384', '32768', '50000'}, (name, result)
    return result

dense = metrics('qwen27_dense_f16_tile128_64k_solo_fix_20261109')
moe = metrics('qwen35_f16_tile128_tile128_20261109')
initial = json.loads((repo / 'results/runtime_experiments/model_loading_sequences/qwen27-dense-f16-tile128-20261109/terminal.json').read_text())
prep = json.loads((out / 'terminal.json').read_text())
fixed = json.loads((repo / 'results/runtime_experiments/model_loading_sequences/qwen27-dense-f16-tile128-64k-solo-fix-20261109/terminal.json').read_text())
assert initial['status'] == 'failed' and prep['stages']['prepare_f16'] == 'passed'
assert fixed['status'] == 'passed'

receipt = {
    'dense_model': 'Qwen3.6 27B Q4_K_M',
    'moe_model': 'Qwen3.6 35B-A3B Q4_K_XL',
    'layout': 'weights on GPU0 3090; one F16 KV worker on GPU1 GTX 1060; 128-thread Pascal head-256 attention tile',
    'worker_context_cap_dense': 65536,
    'worker_context_cap_moe': 262144,
    'generated_tokens_per_depth': 64,
    'dense': dense,
    'moe': moe,
    'moe_over_dense_tps': {d: round(moe[d]['tps'] / dense[d]['tps'], 3) for d in dense},
    'campaign_status': {'full_reservation_probe': initial['status'], 'dense_state_preparation': prep['stages']['prepare_f16'], 'first_solo_replay': prep['stages']['solo_replay'], 'guard_corrected_solo_replay': fixed['status']},
}
(out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

old = Path('/data/bench-staging/kvchat-f16-tile128-20261109-src/examples/simple/simple.cpp').read_text().splitlines(keepends=True)
new = Path('/data/bench-staging/kvchat-dense-f16-tile128-64k-20261109-src/examples/simple/simple.cpp').read_text().splitlines(keepends=True)
patch = ''.join(difflib.unified_diff(old, new, fromfile='a/examples/simple/simple.cpp', tofile='b/examples/simple/simple.cpp'))
assert len([x for x in patch.splitlines() if x.startswith('+') and not x.startswith('+++')]) == 1
(out / 'replay_guard.patch').write_text(patch)
