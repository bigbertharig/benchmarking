from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

RUNNER = Path(__file__).resolve().parents[1] / 'scripts/integration/harness_session_trial.py'
spec = importlib.util.spec_from_file_location('harness_session_trial', RUNNER)
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


def test_fact_cases_respect_four_turn_boundary():
    plan = trial.trial_plan()
    assert len(plan['recent_correction']) - 1 <= 4
    assert len(plan['outside_window']) - 1 > 4
    assert len(plan['two_checkpoints']) == 11
    assert 'NOVA' not in ' '.join(plan['two_checkpoints'][7:])
    assert all('NOVA' not in text and 'Nila' not in text
               for text in plan['outside_window'][-5:-1])
    assert trial.score('NOVA, Nila', final=True)['passed']
    assert not trial.score('ORBIT, Mara', final=True)['passed']
    assert not trial.score('NOVA, Nila; old ORBIT', final=True)['passed']
    assert trial.score('NOVA, Nila\nEvidence: ORBIT and Mara are obsolete', final=True)['passed']
    assert trial.score('anything', final=False) is None


def test_ready_requires_exact_model_identity():
    packet = {'data': [{'id': 'gpu-rig/example', 'model': 'example:1b', 'state': 'ready'}]}
    with patch.object(trial, 'request', return_value=packet):
        assert trial.ready('http://gateway', 'gpu-rig/example', 'example:1b') == packet['data'][0]
        with pytest.raises(RuntimeError, match='not ready'):
            trial.ready('http://gateway', 'gpu-rig/example', 'other:1b')


def test_run_turn_waits_for_terminal_receipt():
    start = {'schema': trial.SCHEMA, 'run_id': 'run-1', 'state': 'running'}
    finish = {'schema': trial.SCHEMA, 'run_id': 'run-1', 'state': 'succeeded',
              'receipt': {'answer': 'ACK'}}
    with patch.object(trial, 'request', side_effect=[start, finish]) as send, \
         patch.object(trial.time, 'sleep'):
        assert trial.run_turn('http://harness', 'token', {'timeout_s': 10}) == finish
    assert send.call_count == 2
