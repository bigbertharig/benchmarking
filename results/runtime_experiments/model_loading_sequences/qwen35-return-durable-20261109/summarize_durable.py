#!/usr/bin/env python3
"""Summarize the single-worker durable return checkpoint campaigns."""
import json
import re
from pathlib import Path

repo=Path('/mnt/shared/plans/shoulders/benchmarking')
raw=Path('/mnt/shared/experiments/kv-matrix-20261107')
result=repo/'results/runtime_experiments/model_loading_sequences/qwen35-return-durable-20261109'

def fields(line):
    out={}
    for key,value in re.findall(r'([a-z_]+)=([^ ]+)',line):
        if re.fullmatch(r'-?\d+',value): out[key]=int(value)
        elif re.fullmatch(r'-?\d+\.\d+',value): out[key]=float(value)
        else: out[key]=value
    return out

def tagged(stem,tag):
    path=raw/(stem+'.log')
    return [fields(line) for line in path.read_text().splitlines() if line.startswith(tag)]

def terminal(folder,status):
    data=json.loads((repo/'results/runtime_experiments/model_loading_sequences'/folder/'terminal.json').read_text())
    assert data['status']==status,(folder,data)
    return {'status':status,'finished_at':data['finished_at'],'stages':data['stages']}

receipt={'model':'Qwen3.6-35B-A3B Q4_K_XL','worker_kv':'Q4_1','context_reservation':262144,
         'checkpoint_format':'atomic base plus one fsynced outbound/return record per completed turn'}
receipt['campaigns']={
 'shared_initial':terminal('qwen35-return-durable-20261109','failed'),
 'shared_resume_fix':terminal('qwen35-return-durable-resume-fix-20261109','passed'),
 'nvme':terminal('qwen35-return-durable-nvme-20261109','passed'),
 'guards':terminal('qwen35-return-durable-guards-20261109','passed')}
receipt['shared']={}
for label in ('start','abort','resume_fix','verify_fix'):
    stem=f'qwen35_return_durable_{label}_20261109'
    item={'recover':tagged(stem,'DURABLE_RECOVER '),'verify':tagged(stem,'DURABLE_VERIFY '),
          'turn':tagged(stem,'DURABLE_TURN ')}
    receipt['shared'][label]=item
assert receipt['shared']['resume_fix']['recover'][0]['ignored_pending']==1
assert receipt['shared']['verify_fix']['verify'][0]['equal']==1
receipt['nvme']={}
for label in ('start','resume','verify'):
    stem=f'qwen35_return_durable_nvme_{label}_20261109'
    receipt['nvme'][label]={'recover':tagged(stem,'DURABLE_RECOVER '),
                            'verify':tagged(stem,'DURABLE_VERIFY '),
                            'turn':tagged(stem,'DURABLE_TURN ')}
assert receipt['nvme']['verify']['verify'][0]['equal']==1
receipt['guards']={
 'base_only':tagged('qwen35_return_durable_guard_base_only_20261109','DURABLE_RECOVER ')[0],
 'corrupt_reject':tagged('qwen35_return_durable_guard_corrupt_reject_20261109','DURABLE_REJECT ')[0],
 'corrupt_exit':int((raw/'qwen35_return_durable_guard_corrupt_reject_20261109.exit').read_text())}
assert receipt['guards']['base_only']['committed']==0
assert receipt['guards']['corrupt_reject']['reason']=='checksum' and receipt['guards']['corrupt_exit']==75
shared=raw/'qwen35_return_durable_20261109.checkpoint'
nvme=Path('/data/bench-staging/return-durable-nvme-20261109/checkpoint')
receipt['checkpoint_files']={
 'shared':{p.name:p.stat().st_size for p in shared.iterdir() if p.is_file()},
 'nvme':{p.name:p.stat().st_size for p in nvme.iterdir() if p.is_file()}}
(result/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'shared_record_write_s':[receipt['shared']['start']['turn'][0]['record_write_s'],
                                          receipt['shared']['resume_fix']['turn'][0]['record_write_s']],
                  'nvme_record_write_s':[receipt['nvme']['start']['turn'][0]['record_write_s'],
                                        receipt['nvme']['resume']['turn'][0]['record_write_s']],
                  'corrupt_exit':receipt['guards']['corrupt_exit']},indent=2))
