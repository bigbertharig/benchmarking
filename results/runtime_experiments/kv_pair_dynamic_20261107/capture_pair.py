from pathlib import Path
import difflib
import hashlib
import json
import re
import shutil

base = Path('/data/bench-staging/strata-v0.2.10/install/third_party/llama.cpp')
source = Path('/mnt/shared/experiments/kvchat-20261106/llama.cpp')
work = Path('/mnt/shared/experiments/kvpair-20261106')
out = Path('/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments/kv_pair_dynamic_20261107')
out.mkdir(parents=True, exist_ok=True)

paths = ['src/llama-kv-cache.cpp', 'src/llama-context.cpp', 'src/llama-graph.cpp',
         'src/llama-kv-chat-device.h', 'examples/simple/simple.cpp']
diff = []
hashes = {}
for path in paths:
    before = base / path
    after = source / path
    old = before.read_text().splitlines(keepends=True) if before.exists() else []
    new = after.read_text().splitlines(keepends=True)
    hashes[path] = hashlib.sha256(before.read_bytes()).hexdigest() if before.exists() else None
    diff.extend(difflib.unified_diff(old, new,
                                    fromfile='a/' + path if before.exists() else '/dev/null',
                                    tofile='b/' + path))
(out / 'private_llama_kv_pair.patch').write_text(''.join(diff))

for name in ['kvpair_modify_pair.py', 'kvpair_replace_harness.py', 'fix_ordinal.py',
             'fix_filter_ordinal.py', 'run_pair.sh', 'capture_pair.py']:
    shutil.copy2(work / name, out / name)
labels = ['smoke_1_7b', 'qwen27_pair256k', 'smoke_1_7b_v2',
          'qwen27_pair256k_v2', 'qwen27_pair256k_v3']
for label in labels:
    for suffix in ['log', 'gpu.csv', 'start', 'finish', 'exit']:
        file = work / f'{label}.{suffix}'
        if file.exists():
            shutil.copy2(file, out / file.name)

def summarize(label):
    log = work / f'{label}.log'
    if not log.exists():
        return None
    text = log.read_text(errors='replace')
    peaks = {}
    for line in (work / f'{label}.gpu.csv').read_text(errors='replace').splitlines():
        m = re.search(r',\s*([0-5]),\s*(\d+) MiB', line)
        if m:
            gpu, used = m.groups()
            peaks[gpu] = max(peaks.get(gpu, 0), int(used))
    exit_file = work / f'{label}.exit'
    return {
        'exit': int(exit_file.read_text().strip()) if exit_file.exists() else None,
        'additions': re.findall(r'ADD_CHAT pair=(\S+) single=(\S+) ctx=(\d+)', text),
        'kv_buffers_mib': re.findall(r'llama_kv_cache:\s+CUDA(\d+) KV buffer size =\s+([\d.]+) MiB', text),
        'first_tokens': re.findall(r'CHAT pair=(\S+) single=(\S+) step=0 token=\d+ text=(.*)', text),
        'phases': re.findall(r'(PHASE_\d+_READY[^\n]*)', text),
        'sampled_peak_mib': peaks,
        'model_buffer_mib': re.findall(r'CUDA0 model buffer size =\s+([\d.]+) MiB', text),
    }

manifest = {'source': str(source), 'base': str(base), 'base_sha256': hashes,
            'runs': {label: summarize(label) for label in labels}}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest['runs'], indent=2))
