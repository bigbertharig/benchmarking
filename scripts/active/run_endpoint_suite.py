#!/usr/bin/env python3
"""Evaluate an explicit HTTP provider and local model record without runtime services."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4
from benchmark_records import validate_record


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def evaluate(config, dataset):
    if not isinstance(config, dict) or config.get('schema') != 'benchmark-endpoint/1':
        raise ValueError('unsupported endpoint configuration schema')
    endpoint = config.get('endpoint', '')
    parsed = urlsplit(endpoint)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('endpoint must be HTTP(S), without credentials, query or fragment')
    model = config.get('model')
    if not isinstance(model, dict) or not all(isinstance(model.get(k), str) and model[k] for k in ('id', 'route', 'revision')):
        raise ValueError('local model record requires id, route and revision')
    if not isinstance(dataset, dict) or dataset.get('schema') != 'benchmark-exact-match/1' or not dataset.get('id'):
        raise ValueError('unsupported dataset schema')
    cases = dataset.get('cases')
    if not isinstance(cases, list) or not cases or len(cases) > 10000:
        raise ValueError('dataset requires 1..10000 cases')
    identifiers = set()
    for case in cases:
        if not isinstance(case, dict) or not all(isinstance(case.get(k), str) and case[k] for k in ('id', 'prompt', 'expected')) or case['id'] in identifiers:
            raise ValueError('case requires unique id, prompt and expected answer')
        identifiers.add(case['id'])
    limit = config.get('max_tokens', 256)
    timeout = config.get('timeout_seconds', 60)
    if type(limit) is not int or not 1 <= limit <= 32768 or type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError('invalid output or timeout bound')
    headers = {'Content-Type': 'application/json'}
    key = os.environ.get(config.get('api_key_env', 'BENCHMARK_API_KEY'))
    if key:
        headers['Authorization'] = 'Bearer ' + key
    started = datetime.now(timezone.utc).isoformat()
    rows = []
    for case in cases:
        tick = time.monotonic()
        row = {'id': case['id'], 'passed': False}
        body = {'model': model['route'], 'messages': [{'role': 'user', 'content': case['prompt']}], 'max_tokens': limit}
        # Explicit experiment settings belong to Benchmarking and are preserved in the receipt.
        if 'generation' in config:
            settings = config['generation']
            if not isinstance(settings, dict) or set(settings) - {'temperature', 'top_p', 'seed', 'presence_penalty', 'frequency_penalty'}:
                raise ValueError('unsupported generation settings')
            body.update(settings)
        try:
            request = Request(endpoint.rstrip('/') + '/chat/completions', data=json.dumps(body).encode(), headers=headers)
            with urlopen(request, timeout=timeout) as response:
                packet = json.load(response)
            answer = packet['choices'][0]['message']['content']
            if not isinstance(answer, str):
                raise ValueError('provider returned no text answer')
            row.update(answer=answer, passed=answer.strip() == case['expected'].strip(),
                       served_model=packet.get('model'), usage=packet.get('usage'), provider_request_id=packet.get('id'))
        except Exception as exc:
            row['error'] = type(exc).__name__
        row['duration_seconds'] = round(time.monotonic() - tick, 6)
        rows.append(row)
    failures = sum('error' in row for row in rows)
    score = sum(row['passed'] for row in rows) / len(rows)
    record = {'schema_version': 3, 'run_id': uuid4().hex, 'run_at': started,
              'model': model['id'], 'test_id': dataset['id'], 'status': 'failure' if failures else 'success',
              'run_class': 'smoke', 'sample_count': len(rows), 'score': score, 'score_pct': score * 100,
              'metric': 'exact_match', 'runtime': {'kind': 'configured_endpoint', 'endpoint': endpoint},
              'efficiency': {'telemetry': None, 'telemetry_status': 'not_collected_endpoint_only'},
              'failure': {'kind': 'provider_error', 'count': failures} if failures else {},
              'methodology': {'id': 'endpoint-exact-match', 'version': '1.0.0', 'comparison_group': dataset['id'] + ':' + digest(dataset)},
              'model_record': model, 'config_sha256': digest(config), 'dataset_sha256': digest(dataset),
              'generation': config.get('generation', {}), 'cases': rows,
              'finished_at': datetime.now(timezone.utc).isoformat()}
    validate_record(record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    record = evaluate(json.loads(args.config.read_text()), json.loads(args.dataset.read_text()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # An explicit new output is required; previous measurements are never overwritten.
    with args.out.open('x') as output:
        output.write(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'status': record['status'], 'score': record['score'], 'receipt': str(args.out)}))
    return 0 if record['status'] == 'success' else 1

if __name__ == '__main__':
    raise SystemExit(main())
