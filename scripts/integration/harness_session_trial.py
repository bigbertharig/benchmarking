#!/usr/bin/env python3
"""Compare bounded Harness turn retention across ready local models.

One invocation tests one externally prepared route. Run separate invocations for each
model and keep their receipts under results/. This runner never loads a model.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 'harness-control/1'
TERMINAL = {'succeeded', 'failed', 'cancelled'}


def request(url: str, *, token: str | None = None, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError('non-object API response')
    return result


def ready(gateway: str, route: str, model: str) -> dict:
    packet = request(gateway + '/v1/rig/ready-roster')
    matches = [row for row in packet.get('data', []) if row.get('id') == route]
    if len(matches) != 1 or matches[0].get('state') != 'ready' or matches[0].get('model') != model:
        raise RuntimeError(f'route {route} is not ready with expected model {model}')
    return matches[0]


def trial_plan() -> dict[str, list[str]]:
    return {
        'recent_correction': [
            'For a memory check, the current project label is ORBIT and the owner is Mara. Reply ACK only.',
            'Correction: the owner is now Nila; Mara is obsolete. Reply ACK only.',
            'Correction: the project label is now NOVA; ORBIT is obsolete. Reply ACK only.',
            'Using only earlier user messages in this conversation as evidence, give the current fictional project label and owner on one line. Omit old values and explanation.',
        ],
        'two_checkpoints': [
            'For a memory check, the current project label is ORBIT and the owner is Mara. Reply ACK only.',
            'Correction: the owner is now Nila and the project label is NOVA; Mara and ORBIT are obsolete. Reply ACK only.',
            'Control step one. Reply ACK only.',
            'Checkpoint one: using this conversation, state the current fictional project label and owner on one line. Omit old values and explanation.',
            'Control step two. Reply ACK only.',
            'Control step three. Reply ACK only.',
            'Checkpoint two: use the earlier checkpoint to state the current fictional project label and owner on one line. Omit old values and explanation.',
            'Control step four. Reply ACK only.',
            'Control step five. Reply ACK only.',
            'Control step six. Reply ACK only.',
            'Using the last checkpoint in this conversation as evidence, give the current fictional project label and owner on one line. Omit old values and explanation.',
        ],
        'outside_window': [
            'For a memory check, the current project label is ORBIT and the owner is Mara. Reply ACK only.',
            'Correction: the owner is now Nila and the project label is NOVA; Mara and ORBIT are obsolete. Reply ACK only.',
            'Control step one. Reply ACK only.',
            'Control step two. Reply ACK only.',
            'Control step three. Reply ACK only.',
            'Control step four. Reply ACK only.',
            'Using only earlier user messages in this conversation as evidence, give the current fictional project label and owner on one line. Omit old values and explanation.',
        ],
    }


def score(answer: str, *, final: bool) -> dict | None:
    if not final:
        return None
    low = answer.lower()
    headline = low.splitlines()[0] if low.splitlines() else ''
    return {'passed': 'nova' in headline and 'nila' in headline
            and 'orbit' not in headline and 'mara' not in headline,
            'current_label': 'nova' in headline, 'current_owner': 'nila' in headline,
            'superseded_label': 'orbit' in headline, 'superseded_owner': 'mara' in headline,
            'obsolete_mentioned_in_evidence': 'orbit' in low or 'mara' in low}


def save(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    tmp.replace(path)


def run_turn(harness: str, token: str, task: dict, *, poll_seconds: float = 2) -> dict:
    accepted = request(harness + '/v1/runs', token=token, body=task)
    if accepted.get('schema') != SCHEMA or not isinstance(accepted.get('run_id'), str):
        raise ValueError('invalid Harness run acceptance')
    run_id = accepted['run_id']
    deadline = time.monotonic() + task['timeout_s'] + 45
    while accepted.get('state') not in TERMINAL:
        if time.monotonic() >= deadline:
            raise TimeoutError(f'Harness run {run_id} exceeded poll deadline')
        time.sleep(poll_seconds)
        accepted = request(harness + '/v1/runs/' + run_id, token=token)
    if accepted.get('schema') != SCHEMA or accepted.get('run_id') != run_id:
        raise ValueError('Harness run status changed identity')
    return accepted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, help='Gateway ready-roster profile ID')
    parser.add_argument('--model', required=True, help='Exact served model identity')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--case', action='append', choices=sorted(trial_plan()),
                        help='Run only selected case(s); repeat to select multiple')
    parser.add_argument('--gateway', default='http://127.0.0.1:8080')
    parser.add_argument('--harness', default='http://127.0.0.1:8091')
    args = parser.parse_args()
    token = os.environ.get('HARNESS_SERVICE_TOKEN')
    if not token:
        parser.error('HARNESS_SERVICE_TOKEN is required')
    gateway, harness = args.gateway.rstrip('/'), args.harness.rstrip('/')
    route = 'gpu-rig/' + args.profile
    before = ready(gateway, route, args.model)
    report = {'schema': 'harness-session-trial/1', 'started_at': datetime.now(timezone.utc).isoformat(),
              'profile': args.profile, 'model': args.model, 'route': route,
              'roster_before': before, 'cases': {}, 'scorer_revision': 2, 'complete': False}
    save(args.out, report)
    try:
        for case, prompts in trial_plan().items():
            if args.case and case not in args.case:
                continue
            conversation = 'bench-' + uuid.uuid4().hex
            parent = None
            rows = []
            report['cases'][case] = {'conversation_id': conversation, 'turns': rows}
            for index, prompt in enumerate(prompts):
                task = {'schema': SCHEMA, 'request_id': 'bench-' + uuid.uuid4().hex,
                        'conversation_id': conversation, 'prompt': prompt,
                        'agent_type': 'coding', 'tool_profile': 'none',
                        'route': route, 'expected_model': args.model,
                        'max_tokens': 1024, 'timeout_s': 180, 'max_tool_calls': 1}
                if parent:
                    task['parent_run_id'] = parent
                started = time.monotonic()
                status = run_turn(harness, token, task)
                receipt = status.get('receipt') or {}
                row = {'index': index, 'prompt': prompt, 'run_id': status['run_id'],
                       'parent_run_id': parent, 'state': status['state'],
                       'answer': receipt.get('answer'), 'error': receipt.get('error'),
                       'duration_s': round(time.monotonic() - started, 2),
                       'prior_turns_used': receipt.get('prior_turns_used'),
                       'model_steps': receipt.get('model_steps'),
                       'prompt_tokens': sum(call.get('usage', {}).get('prompt_tokens', 0)
                                            for call in receipt.get('model_call_receipts', [])),
                       'completion_tokens': sum(call.get('usage', {}).get('completion_tokens', 0)
                                                for call in receipt.get('model_call_receipts', [])),
                       'model_latency_ms': sum(call.get('latency_ms', 0)
                                               for call in receipt.get('model_call_receipts', [])),
                       'output_limit_hit': receipt.get('limits', {}).get('output_limit_hit'),
                       'score': score(receipt.get('answer') or '',
                                      final=index == len(prompts)-1 or
                                      (case == 'two_checkpoints' and index in (3, 6)))}
                rows.append(row)
                save(args.out, report)
                if status['state'] != 'succeeded':
                    raise RuntimeError(f'{case} turn {index} ended {status["state"]}: {receipt.get("error")}')
                parent = status['run_id']
            report['cases'][case]['passed'] = bool(rows[-1]['score']['passed'])
            if case == 'two_checkpoints':
                report['cases'][case]['checkpoints_passed'] = [rows[i]['score']['passed'] for i in (3, 6)]
            save(args.out, report)
        after = ready(gateway, route, args.model)
        report['roster_after'] = after
        report['roster_unchanged'] = before == after
        report['complete'] = True
    except Exception as exc:
        report['failure'] = f'{type(exc).__name__}: {exc}'
        save(args.out, report)
        raise
    save(args.out, report)
    print(json.dumps({'out': str(args.out.resolve()), 'profile': args.profile,
                      'cases': {name: data['passed'] for name, data in report['cases'].items()},
                      'roster_unchanged': report['roster_unchanged']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
