#!/usr/bin/env python3
"""Reduce the managed PLE bus probe log and sampled link states."""
import argparse
import collections
import json
import pathlib

ap = argparse.ArgumentParser()
ap.add_argument('--log', type=pathlib.Path, required=True)
ap.add_argument('--links', type=pathlib.Path, required=True)
ap.add_argument('--output', type=pathlib.Path, required=True)
args = ap.parse_args()
measurements = []
for line in args.log.read_text().splitlines():
    if line.startswith('{"kind":'):
        item = json.loads(line)
        if item['kind'].startswith('gpu_bulk_') or item['kind'].startswith('gpu_local_'):
            item['throughput_gib_s'] = round(item['bytes'] / (item['mean_us'] * 1e-6) / 2**30, 3)
        measurements.append(item)
if len(measurements) != 18:
    raise ValueError(f'expected 18 measurements, got {len(measurements)}')
states = collections.defaultdict(collections.Counter)
for line in args.links.read_text().splitlines():
    fields = [x.strip() for x in line.split(',')]
    if len(fields) != 5 or fields[0] not in ('1', '2'):
        continue
    states[fields[2]][f'Gen{fields[3]} x{fields[4]}'] += 1
report = {'schema': 'ple-bus-probe-summary/1', 'measurements': measurements,
          'sampled_link_states': {bus: dict(counts) for bus, counts in states.items()}}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'measurements': len(measurements), 'link_states': report['sampled_link_states']}))
