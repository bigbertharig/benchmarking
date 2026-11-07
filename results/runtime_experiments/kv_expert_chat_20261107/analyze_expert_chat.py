from pathlib import Path
import json
import re

root = Path('/mnt/shared/experiments/kv-expert-chat-20261107')
cases = [
    'nemo_layer_chat_256',
    'nemo_experts1234_chat_256',
    'nemo_experts1235_chat_256',
    'nemo_layer5_chat_256',
    'nemo_layer5_depth_128',
    'nemo_experts1234_depth_128',
]
result = {}
for label in cases:
    path = root / (label + '.log')
    if not path.exists():
        continue
    log = path.read_text(errors='replace')
    phases = {}
    for name, chats, tokens, seconds, rate, ok in re.findall(
        r'^PARALLEL phase=(\S+) chats=(\d+) tokens_each=(\d+) seconds=([\d.]+) aggregate_tps=([\d.]+) ok=(\d+)$',
        log, re.M,
    ):
        phases[name] = {
            'chats': int(chats), 'tokens_each': int(tokens),
            'seconds': float(seconds), 'aggregate_tps': float(rate),
            'ok': ok == '1',
        }
    max_gpu_mib = {}
    csv = root / (label + '.gpu.csv')
    if csv.exists():
        for line in csv.read_text(errors='replace').splitlines():
            match = re.search(r',\s*(\d+),\s*(\d+) MiB,', line)
            if match:
                card, value = int(match[1]), int(match[2])
                max_gpu_mib[str(card)] = max(value, max_gpu_mib.get(str(card), 0))
    first = re.findall(r'^FIRST name=(\S+) token=\d+ text=(.*)$', log, re.M)
    bench = [
        {'name': name, 'phase': phase, 'used': int(used),
         'tokens': int(tokens), 'seconds': float(seconds), 'tps': float(rate)}
        for name, phase, used, tokens, seconds, rate in re.findall(
            r'^BENCH name=(\S+) phase=(\S+) used=(\d+) tokens=(\d+) seconds=([\d.]+) tps=([\d.]+)$',
            log, re.M,
        )
    ]
    fill = [
        {'name': name, 'target': int(target), 'seconds': float(seconds),
         'tps': float(rate)}
        for name, target, seconds, rate in re.findall(
            r'^FILL_DONE name=(\S+) target=(\d+) seconds=([\d.]+) tps=([\d.]+)$',
            log, re.M,
        )
    ]
    result[label] = {
        'exit': (root / (label + '.exit')).read_text().strip()
                if (root / (label + '.exit')).exists() else None,
        'one_weight_load': log.count('MODEL_READY one weight load') == 1,
        'placement': re.findall(r'^MODEL_PLACEMENT .*$', log, re.M),
        'overrides': re.findall(r'^TENSOR_OVERRIDE .*$', log, re.M),
        'model_buffers_mib': dict(re.findall(
            r'^load_tensors:\s+CUDA(\d+) model buffer size =\s+([\d.]+) MiB$',
            log, re.M,
        )),
        'max_gpu_mib': max_gpu_mib,
        'first_tokens': dict(first),
        'bench': bench,
        'fill': fill,
        'phases': phases,
    }
    result[label]['valid'] = (
        result[label]['exit'] == '0'
        and result[label]['one_weight_load']
        and len(phases) == 2
        and all(phase['ok'] for phase in phases.values())
        and result[label]['first_tokens'] == {
            'worker4': ' Tokyo', 'worker5': ' Berlin',
            'large_pair45': ' Ottawa',
        }
        and (not label.endswith('depth_128') or (
            len(fill) == 6
            and len(bench) == 6
            and all(row['used'] >= (7372 if row['name'] != 'large_pair45' else 29491)
                    for row in bench if row['phase'] == 'depth90')
        ))
    )

base = result.get('nemo_layer_chat_256', {}).get('phases', {})
depth_base = result.get('nemo_layer5_depth_128', {}).get('phases', {})
for name, row in result.items():
    row['vs_four_card_baseline'] = {
        phase: round(value['aggregate_tps'] / base[phase]['aggregate_tps'], 3)
        for phase, value in row['phases'].items() if phase in base
    }
    row['vs_five_card_depth_baseline'] = {
        phase: round(value['aggregate_tps'] / depth_base[phase]['aggregate_tps'], 3)
        for phase, value in row['phases'].items() if phase in depth_base
    }
(root / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({name: {
    'exit': row['exit'], 'valid': row['valid'],
    'rates': {phase: value['aggregate_tps'] for phase, value in row['phases'].items()},
    'vs_four_card_baseline': row['vs_four_card_baseline'],
    'max_gpu_mib': row['max_gpu_mib'],
} for name, row in result.items()}, indent=2))
