#!/usr/bin/env python3
"""Build a compact receipt from the saved one-worker return-path logs."""
import json
import re
from pathlib import Path

raw = Path('/mnt/shared/experiments/kv-matrix-20261107')
out = Path('/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments/model_loading_sequences/qwen35-return-delta-20261109')
seq = out.parent

def fields(line):
    result = {}
    for key, value in re.findall(r'([a-z_]+)=([^ ]+)', line):
        if re.fullmatch(r'-?\d+', value):
            result[key] = int(value)
        elif re.fullmatch(r'-?\d+\.\d+', value):
            result[key] = float(value)
        else:
            result[key] = value
    return result

def lines(stem, prefix):
    path = raw / (stem + '.log')
    result = [fields(line) for line in path.read_text().splitlines() if line.startswith(prefix)]
    assert result, (path, prefix)
    return result

def passed(folder):
    data = json.loads((seq / folder / 'terminal.json').read_text())
    assert data['status'] == 'passed', data
    return data['finished_at']

receipt = {'model': 'Qwen3.6-35B-A3B Q4_K_XL',
           'worker_kv': 'Q4_1', 'worker_gpu': 1, 'model_gpu': 0,
           'reservation_tokens': 262144, 'return_path': 'host base checkpoint plus append updates'}
receipt['two_turn_finish'] = passed('qwen35-return-delta-20261109')
two = {}
for depth in (50000, 100000, 200000):
    item = {'return': lines(f'qwen35_return_delta_{depth}_return_20261109', 'RETURN_DELTA '),
            'verify': lines(f'qwen35_return_delta_{depth}_return_20261109', 'RETURN_VERIFY ')[0]}
    assert len(item['return']) == 2 and item['verify']['equal'] == 1
    if depth != 50000:
        for control in ('control_before', 'control_after'):
            item[control] = lines(f'qwen35_return_delta_{depth}_{control}_20261109', 'TURN_AB ')
            assert len(item[control]) == 2
    two[str(depth)] = item
receipt['two_turn'] = two

receipt['chain10_finish'] = passed('qwen35-return-chain10-v2-20261109')
chain10 = 'qwen35_return_chain10_v2_200000_20261109'
receipt['chain10'] = {'turns': lines(chain10, 'RETURN_DELTA '),
                      'verify': lines(chain10, 'RETURN_VERIFY ')[0]}
assert len(receipt['chain10']['turns']) == 10 and receipt['chain10']['verify']['equal'] == 1

receipt['compact20_finish'] = passed('qwen35-return-compact20-20261109')
twenty = {}
for mode in ('none', 'compact'):
    stem = f'qwen35_return_compact20_{mode}_20261109'
    item = {'turns': lines(stem, 'RETURN_DELTA '),
            'verify': lines(stem, 'RETURN_VERIFY ')[0]}
    assert len(item['turns']) == 20 and item['verify']['equal'] == 1
    item['turn_s_sum'] = round(sum(turn['total_s'] for turn in item['turns']), 3)
    item['turns_11_20_s_sum'] = round(sum(turn['total_s'] for turn in item['turns'][10:]), 3)
    if mode == 'compact':
        item['compactions'] = lines(stem, 'RETURN_COMPACT ')
        assert len(item['compactions']) == 2
    twenty[mode] = item
receipt['twenty_turn'] = twenty
receipt['twenty_turn']['saved_turn_s_11_20'] = round(twenty['none']['turns_11_20_s_sum'] - twenty['compact']['turns_11_20_s_sum'], 3)
receipt['twenty_turn']['net_saved_through_turn20_s'] = round(twenty['none']['turn_s_sum'] - twenty['compact']['turn_s_sum'] - twenty['compact']['compactions'][0]['compact_s'], 3)
receipt['twenty_turn']['net_saved_including_turn20_compaction_s'] = round(twenty['none']['turn_s_sum'] - twenty['compact']['turn_s_sum'] - sum(c['compact_s'] for c in twenty['compact']['compactions']), 3)

(out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({'two_turn_finish': receipt['two_turn_finish'],
                  'chain10_finish': receipt['chain10_finish'],
                  'compact20_finish': receipt['compact20_finish'],
                  'twenty_turn_saved_11_20_s': receipt['twenty_turn']['saved_turn_s_11_20'],
                  'net_saved_through_20_s': receipt['twenty_turn']['net_saved_through_turn20_s'],
                  'net_saved_including_final_compact_s': receipt['twenty_turn']['net_saved_including_turn20_compaction_s']}, indent=2))
