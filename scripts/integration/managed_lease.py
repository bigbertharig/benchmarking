#!/usr/bin/env python3
"""Benchmark lease client for explicit Orchestration controller authority."""
import os,sys
from uuid import uuid4
from orchestration_client import lifecycle


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv: raise ValueError('lease action required')
    action,*args=argv
    controller=os.environ.get('BENCHMARK_CONTROLLER')
    if not controller:
        raise ValueError('BENCHMARK_CONTROLLER must name the already-active runtime controller')
    def call(operation,**fields):return lifecycle(operation,request_id=uuid4().hex,controller=controller,**fields)
    if action=='acquire':
        gpu,owner,run_id,*rest=args
        model=rest[0] if rest else '';claim=rest[1] if len(rest)>1 else ''
        spec={'controller':'benchmarks','owner':owner,'run_id':run_id,'gpu_ids':[int(v) for v in gpu.split(',')],
              'ttl_s':600,'metadata':{'model':model,**({'claim':claim} if claim else {})}}
        print(call('lease.acquire',spec=spec)['lease']['lease_id'])
    elif action in ('renew','release'):
        lease_id,owner=args
        if not lease_id:raise ValueError('managed lease ID is required')
        call('lease.'+action,lease_id=lease_id,owner=owner,ttl_s=600)
    elif action=='reserve':
        gpus,name,owner,*rest=args
        call('claim.add',name=name,owner=owner,gpu_ids=[int(v) for v in gpus.split(',')],model=rest[0] if rest else '',ttl_s=600)
    elif action=='renew-reservation':
        name,owner=args;call('claim.renew',name=name,owner=owner,ttl_s=600)
    elif action=='unreserve':
        name,=args;call('claim.remove',name=name)
    else:raise ValueError('unsupported lease action')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Managed admission refused: '+str(exc),file=sys.stderr);raise SystemExit(2)
