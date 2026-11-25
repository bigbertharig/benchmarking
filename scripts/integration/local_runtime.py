#!/usr/bin/env python3
"""Explicit local-profile client. Hardware effects stay in Orchestration."""
import argparse,json,os
from pathlib import Path
from uuid import uuid4
from orchestration_client import lifecycle


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['register','load','stop'])
    p.add_argument('--profile',required=True)
    p.add_argument('--spec',type=Path)
    p.add_argument('--gpus',default=os.getenv('BENCHMARK_GPU_IDS','0'))
    p.add_argument('--controller',default=os.getenv('BENCHMARK_CONTROLLER','benchmarks-local'))
    a=p.parse_args()
    def call(operation,**fields): return lifecycle(operation,request_id=uuid4().hex,controller=a.controller,**fields)
    if a.action=='register':
        if a.spec is None:p.error('--spec is required')
        result=call('profile.register',profile_id=a.profile,spec=json.loads(a.spec.read_text()))
    else:
        call('controller.claim')
        fields={'profile_id':a.profile}
        if a.action=='load': fields['gpu_ids']=[int(v) for v in a.gpus.split(',')]
        result=call(a.action,**fields)
    print(json.dumps(result))

if __name__=='__main__':main()
