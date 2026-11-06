#!/usr/bin/env python3
"""Run matched Qwen3.8 Q2_0 Strata placements with the CUDA 12 engine."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('results/runtime_experiments')
CASES = (
    ('g0_cuda12_nvme0p1', '0', 0.1),
    ('g01_cuda12_nvme0p1', '1,0', 0.1),
    ('gall_cuda12_nvme0p1', '1,2,3,4,5,0', 0.1),
    ('gall_cuda12_nvme8', '1,2,3,4,5,0', 8.0),
)

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def save(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    os.replace(tmp, path)

def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: run_strata_qwen38_mixed_campaign.py RUN_ID')
    run_id = sys.argv[1]
    out = ROOT / run_id
    out.mkdir(parents=True, exist_ok=True)
    state = {'run_id': run_id, 'started_at': stamp(), 'status': 'running',
             'engine_dir': os.environ.get('STRATA_COMPONENTS_DIR'), 'cases': []}
    save(out / 'checkpoint.json', state)
    for label, gpus, budget in CASES:
        case_out = ROOT / f'{run_id}_{label}'
        cmd = [sys.executable, 'scripts/integration/run_strata_qwen38_placement.py',
               '--output', str(case_out), '--gpus', gpus, '--context', '8192',
               '--resident-budget-gib', str(budget), '--evict-expert-cache']
        case = {'label': label, 'gpus': gpus, 'resident_budget_gib': budget,
                'output': str(case_out), 'started_at': stamp(), 'command': cmd}
        state['cases'].append(case)
        save(out / 'checkpoint.json', state)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        case['exit_code'] = proc.returncode
        case['stdout_tail'] = proc.stdout[-500:]
        case['stderr_tail'] = proc.stderr[-500:]
        case['finished_at'] = stamp()
        save(out / 'checkpoint.json', state)
    state['status'] = 'passed' if all(x['exit_code'] == 0 for x in state['cases']) else 'failed'
    state['finished_at'] = stamp()
    save(out / 'terminal.json', state)
    print(f"Strata mixed campaign {state['status']}: " + ', '.join(f"{x['label']}={x['exit_code']}" for x in state['cases']), flush=True)
    return 0 if state['status'] == 'passed' else 1

if __name__ == '__main__':
    raise SystemExit(main())
