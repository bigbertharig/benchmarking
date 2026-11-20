#!/usr/bin/env python3
"""Condense nvidia-smi and optional process-memory samples for a vision run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--gpu-index', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be a new file')
    samples = [json.loads(line) for line in args.receipt.read_text(encoding='utf-8').splitlines()
               if line.strip()]
    cards = [card for sample in samples for card in sample.get('gpus', [])
             if card['index'] == args.gpu_index]
    if not cards:
        parser.error('no samples for requested GPU')
    host_available = [sample['host_memory_mib'].get('MemAvailable') for sample in samples
                      if sample.get('host_memory_mib', {}).get('MemAvailable') is not None]
    process_hwm = [proc['memory_mib'].get('VmHWM') for sample in samples
                   for proc in sample.get('watched_processes', [])
                   if proc.get('memory_mib', {}).get('VmHWM') is not None]
    summary = {
        'receipt': str(args.receipt), 'gpu_index': args.gpu_index,
        'samples': len(cards), 'first_sample_at': samples[0]['at'],
        'last_sample_at': samples[-1]['at'],
        'peak_gpu_memory_mib': max(card['memory_mib'] for card in cards),
        'mean_gpu_util_pct': round(statistics.mean(card['util_pct'] for card in cards), 2),
        'peak_power_w': max(card['power_w'] for card in cards),
        'mean_power_w': round(statistics.mean(card['power_w'] for card in cards), 2),
        'peak_temperature_c': max(card['temperature_c'] for card in cards),
        'minimum_host_available_mib': min(host_available) if host_available else None,
        'peak_watched_process_rss_mib': max(process_hwm) if process_hwm else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
