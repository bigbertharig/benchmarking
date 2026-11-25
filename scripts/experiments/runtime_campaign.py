#!/usr/bin/env python3
"""Portable runtime/profile/power campaigns over Orchestration's public lifecycle CLI."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from uuid import uuid4

SCHEMA = 'rig-lifecycle/1'


def runtime_request(command, operation, controller, **fields):
    request_id = fields.pop('request_id', None) or uuid4().hex
    request = dict(schema=SCHEMA, request_id=request_id, operation=operation, controller=controller, **fields)
    result = subprocess.run([*command, 'api', '--request', json.dumps(request)], capture_output=True, text=True, timeout=1200)
    try: receipt = json.loads(result.stdout)
    except ValueError: raise RuntimeError('runtime returned no valid JSON receipt')
    if receipt.get('schema') != SCHEMA or receipt.get('operation') != operation or not receipt.get('ok') or result.returncode:
        raise RuntimeError('runtime refused operation: ' + json.dumps(receipt))
    return receipt


def run(config, output, *, control=runtime_request):
    if config.get('schema') != 'benchmark-runtime-campaign/1':
        raise ValueError('unsupported campaign schema')
    command = config.get('runtime_command', ['rig'])
    if not isinstance(command, list) or not command or not all(isinstance(v,str) and v for v in command):
        raise ValueError('runtime_command must be an argv array')
    controller = config['controller']
    cases = config.get('cases')
    if not isinstance(cases,list) or not cases:
        raise ValueError('cases are required')
    for case in cases:
        endpoint = urlsplit(case.get('endpoint', ''))
        if endpoint.scheme not in ('http', 'https') or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise ValueError('case endpoint must be HTTP(S) without embedded credentials or query')
        settings = case.get('generation', {})
        if not isinstance(settings, dict) or set(settings) - {'temperature','top_p','top_k','min_p','presence_penalty','frequency_penalty','repeat_penalty','seed'}:
            raise ValueError('case generation contains unsupported settings')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'schema': 'benchmark-runtime-campaign-receipt/1', 'state': 'running',
               'started_at': datetime.now(timezone.utc).isoformat(), 'config': config,
               'config_sha256': hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(), 'cases': [], 'requests': []}
    def persist():
        receipt['last_progress_at'] = datetime.now(timezone.utc).isoformat()
        temp = output / 'receipt.tmp'; temp.write_text(json.dumps(receipt,indent=2)+'\n')
        os.replace(temp, output/'receipt.json')
    def op(operation, **fields):
        request_id = fields.pop('request_id', None) or uuid4().hex
        row = {'request_id': request_id, 'operation': operation, 'fields': fields, 'state': 'dispatching'}
        receipt['requests'].append(row); persist()
        try:
            result = control(command,operation,controller,request_id=request_id,**fields)
        except BaseException as exc:
            row.update(state='unresolved', error=str(exc)); persist()
            raise
        row.update(state='completed', receipt=result); persist()
        return result
    persist()
    try:
        op('controller.claim')
        for case in cases:
            pid = case['profile_id']
            repeat = case.get('repeats',3); workers = case.get('workers',1)
            if type(repeat) is not int or not 1<=repeat<=10000 or type(workers) is not int or not 1<=workers<=64:
                raise ValueError('invalid campaign concurrency bounds')
            row = {'id':case['id'], 'samples':[], 'telemetry':None, 'telemetry_status':'not_collected', 'operations':[]}
            receipt['cases'].append(row); persist()
            row['operations'].append(op('profile.register',profile_id=pid,spec=case['spec']))
            loaded = False; power_id = None
            try:
                row['operations'].append(op('load',profile_id=pid,gpu_ids=case['gpu_ids']))
                loaded = True
                if 'power_watts' in case:
                    if len(case['gpu_ids']) != 1:
                        raise ValueError('power campaign case must select exactly one GPU')
                    power_id = uuid4().hex
                    changed = op('power.set',request_id=power_id,gpu_id=case['gpu_ids'][0],watts=case['power_watts'])
                    row['operations'].append(changed)
                def sample(index):
                    started = time.monotonic()
                    payload={'model':case['spec']['model'],'messages':[{'role':'user','content':case['prompt']}],
                             'max_tokens':case.get('max_tokens',256)}
                    payload.update(case.get('generation',{}))
                    headers={'Content-Type':'application/json'}
                    key=os.getenv(config.get('api_key_env','BENCHMARK_API_KEY'))
                    if key: headers['Authorization']='Bearer '+key
                    with urlopen(Request(case['endpoint'].rstrip('/')+'/chat/completions',data=json.dumps(payload).encode(),headers=headers),timeout=600) as response:
                        packet=json.load(response)
                    return {'index':index,'duration_seconds':time.monotonic()-started,'usage':packet.get('usage'),
                            'timings':packet.get('timings'),'served_model':packet.get('model'),'provider_request_id':packet.get('id')}
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    for result in pool.map(sample,range(repeat)):
                        row['samples'].append(result); persist()
                row['state']='complete'
            finally:
                try:
                    if power_id: row['operations'].append(op('power.restore',power_session_id=power_id))
                finally:
                    if loaded: row['operations'].append(op('stop',profile_id=pid))
                persist()
        receipt['state']='complete'
    except BaseException as exc:
        receipt['state']='failed'; receipt['error']=str(exc)
        raise
    finally:
        receipt['finished_at']=datetime.now(timezone.utc).isoformat(); persist()
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args(); run(json.loads(args.config.read_text()),args.out)

if __name__=='__main__': main()
