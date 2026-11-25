#!/usr/bin/env python3
"""Reconcile a stopped runtime campaign's owned power session and model."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4
from runtime_campaign import runtime_request


def run(receipt_path, *, control=runtime_request):
    path = Path(receipt_path)
    campaign = json.loads(path.read_text())
    if campaign.get('schema') != 'benchmark-runtime-campaign-receipt/1':
        raise ValueError('unsupported campaign receipt')
    if campaign.get('state') == 'complete':
        raise ValueError('complete campaign does not need recovery')
    config = campaign.get('config') or {}
    if config.get('schema') != 'benchmark-runtime-campaign/1':
        raise ValueError('unsupported campaign configuration')
    controller = config['controller']
    command = config.get('runtime_command', ['rig'])
    recovery_path = path.parent / 'recovery.json'
    if recovery_path.exists():
        previous = json.loads(recovery_path.read_text())
        if previous.get('state') == 'complete':
            return previous
        raise RuntimeError('prior recovery is incomplete; reconcile its request ID before retrying')
    receipt = {'schema':'benchmark-runtime-campaign-recovery/1', 'state':'running',
               'started_at':datetime.now(timezone.utc).isoformat(),
               'campaign_receipt':str(path), 'requests':[]}
    def persist():
        temp = recovery_path.with_name('recovery.tmp')
        temp.write_text(json.dumps(receipt,indent=2)+'\n')
        os.replace(temp,recovery_path)
    def call(operation, **fields):
        row = {'operation':operation,'request_id':uuid4().hex,'fields':fields,'state':'dispatching'}
        receipt['requests'].append(row);persist()
        try:
            result=control(command,operation,controller,request_id=row['request_id'],**fields)
        except BaseException as exc:
            row.update(state='unresolved',error=str(exc));persist();raise
        row.update(state='completed',receipt=result);persist()
    persist()
    try:
        for case in reversed(campaign.get('cases', [])):
            original=campaign.get('requests', [])
            # Requests are serialized case by case. Bound recovery to this case's
            # register marker so repeated GPU IDs do not cross case ownership.
            cfg=next((x for x in config['cases'] if x['id']==case['id']),None)
            if cfg is None: raise ValueError('case missing from campaign configuration')
            pid=cfg['profile_id']
            start=next((i for i,x in enumerate(original) if x['operation']=='profile.register'
                        and x.get('fields',{}).get('profile_id')==pid),None)
            if start is None: continue
            end=next((i for i in range(start+1,len(original)) if original[i]['operation']=='profile.register'),len(original))
            selected=original[start:end]
            loaded=[x for x in selected if x['operation']=='load']
            if not loaded:continue
            if loaded[-1]['state']!='completed':
                raise RuntimeError('load is unresolved; reconcile the runtime before recovery')
            power=[x for x in selected if x['operation']=='power.set']
            restored=[x for x in selected if x['operation']=='power.restore']
            if any(x['state']!='completed' for x in restored):
                raise RuntimeError('power restore is unresolved; reconcile the original request ID')
            if power and not restored:
                call('power.restore',power_session_id=power[-1]['request_id'])
            stopped=[x for x in selected if x['operation']=='stop']
            if any(x['state']!='completed' for x in stopped):
                raise RuntimeError('model stop is unresolved; reconcile the original request ID')
            if not stopped:call('stop',profile_id=pid)
        receipt['state']='complete'
    except BaseException as exc:
        receipt.update(state='needs_reconciliation',error=str(exc))
        raise
    finally:
        receipt['finished_at']=datetime.now(timezone.utc).isoformat();persist()
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',required=True,type=Path)
    args=parser.parse_args();print(json.dumps(run(args.receipt),indent=2))

if __name__=='__main__':main()
