#!/usr/bin/env python3
"""Measure later-token expert coverage from earlier-token BigMoe routing."""
from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('trace', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()

    with args.trace.open(newline='') as source:
        rows = [row for row in csv.DictReader(line for line in source if not line.startswith('#'))
                if int(row['phase']) == 1]
    steps = sorted({int(row['step']) for row in rows})
    if len(steps) < 8:
        raise SystemExit('need at least eight decode steps')
    pivot = len(steps) // 2
    train_steps = set(steps[:pivot])
    train = collections.defaultdict(collections.Counter)
    test = []
    layer_bytes = {}
    for row in rows:
        layer = int(row['layer'])
        expert = int(row['expert'])
        layer_bytes[layer] = max(layer_bytes.get(layer, 0), int(row['expert_bytes']))
        if int(row['step']) in train_steps:
            train[layer][expert] += 1
        else:
            test.append((layer, expert, float(row['weight'])))
    if not test or len(train) != len(layer_bytes):
        raise SystemExit('training/test split or layer coverage incomplete')
    results = {}
    for budget in (1, 4, 8, 16, 32, 64, 128):
        cached = {layer: {expert for expert, _ in counts.most_common(budget)}
                  for layer, counts in train.items()}
        hit_rows = sum(expert in cached[layer] for layer, expert, _ in test)
        total_weight = sum(weight for _, _, weight in test)
        hit_weight = sum(weight for layer, expert, weight in test
                         if expert in cached[layer])
        results[str(budget)] = {
            'test_route_coverage': round(hit_rows / len(test), 4),
            'test_weight_coverage': round(hit_weight / total_weight, 4),
            'estimated_expert_bytes': sum(value * budget for value in layer_bytes.values()),
        }
    summary = {
        'method': 'top experts per layer by route count in first half of decode steps; evaluate second half',
        'decode_steps': len(steps),
        'training_steps': pivot,
        'test_steps': len(steps) - pivot,
        'training_rows': len(rows) - len(test),
        'test_rows': len(test),
        'layers': len(layer_bytes),
        'budgets': results,
        'limit': 'one prompt and nearby tokens; coverage estimates are not measured cache hits or speedups',
    }
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
