#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path

raw = Path('/mnt/shared/experiments/kv-matrix-20261107')
repo = Path('/mnt/shared/plans/shoulders/benchmarking')
dest = repo / 'results/runtime_experiments/model_loading_sequences/qwen27-dense-f16-trace-50k-20261109'
files = {
    'dense': raw / 'qwen27_dense_f16_tile128_trace_50k_20261109.sqlite',
    'moe': raw / 'qwen35_f16_tile128_trace_tile128_50k_20261109.sqlite',
}

def parse(path):
    db = sqlite3.connect(path)
    one = lambda q: db.execute(q).fetchone()[0] or 0
    out = {}
    for gpu in (0, 1):
        prefix = f'gpu{gpu}'
        out[prefix] = {
            'kernel_ms_sum': round(one(f'SELECT SUM(end-start) FROM CUPTI_ACTIVITY_KIND_KERNEL WHERE deviceId={gpu}') / 1e6, 3),
            'graph_ms_sum': round(one(f'SELECT SUM(end-start) FROM CUPTI_ACTIVITY_KIND_GRAPH_TRACE WHERE deviceId={gpu}') / 1e6, 3),
        }
        for key, pattern in [('attention_tile_ms_sum', 'flash_attn_tile'), ('attention_combine_ms_sum', 'flash_attn_combine')]:
            out[prefix][key] = round(one(f"SELECT SUM(k.end-k.start) FROM CUPTI_ACTIVITY_KIND_KERNEL k JOIN StringIds s ON k.demangledName=s.id WHERE k.deviceId={gpu} AND s.value LIKE '%{pattern}%'") / 1e6, 3)
        for kind in (1, 2, 8, 10):
            count, bytes_, ns = db.execute(f'SELECT COUNT(*),SUM(bytes),SUM(end-start) FROM CUPTI_ACTIVITY_KIND_MEMCPY WHERE deviceId={gpu} AND copyKind={kind}').fetchone()
            if count:
                out[prefix][f'copykind{kind}'] = {'count': count, 'MB': round((bytes_ or 0) / 1e6, 3), 'ms_sum': round((ns or 0) / 1e6, 3)}
        rows = db.execute(f'''SELECT s.value,COUNT(*),SUM(k.end-k.start) FROM CUPTI_ACTIVITY_KIND_KERNEL k
                              JOIN StringIds s ON k.demangledName=s.id WHERE k.deviceId={gpu}
                              GROUP BY s.value ORDER BY SUM(k.end-k.start) DESC LIMIT 8''').fetchall()
        out[prefix]['top_kernels'] = [{'name': name[:170], 'count': count, 'ms_sum': round(ns / 1e6, 3)} for name, count, ns in rows]
    out['gpu1_tile_shape'] = db.execute("SELECT k.gridX,k.gridY,k.gridZ,k.blockX,k.blockY,k.blockZ,k.registersPerThread,k.staticSharedMemory,k.localMemoryPerThread FROM CUPTI_ACTIVITY_KIND_KERNEL k JOIN StringIds s ON k.demangledName=s.id WHERE k.deviceId=1 AND s.value LIKE '%flash_attn_tile%' LIMIT 1").fetchone()
    db.close()
    return out

result = {name: parse(path) for name, path in files.items()}
result['source_reports'] = {name: str(path) for name, path in files.items()}
(dest / 'trace_summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({name: {gpu: {k:v for k,v in result[name][gpu].items() if k != 'top_kernels'} for gpu in ('gpu0', 'gpu1')} for name in ('dense', 'moe')}, indent=2))
