import json
import sqlite3
from pathlib import Path

root = Path('/mnt/shared/experiments/kv-matrix-20261107')
out = {}
for variant in ('control', 'tile256', 'tile128', 'tile64'):
    campaign = variant if variant != 'control' else 'tile256'
    stem = root / f'qwen35_f16_{campaign}_trace_{variant}_50k_20261109'
    db = sqlite3.connect(str(stem) + '.sqlite')
    one = lambda query: db.execute(query).fetchone()[0] or 0
    d = {}
    for gpu in (0, 1):
        d[f'gpu{gpu}_kernel_ms'] = round(one(f'SELECT SUM(end-start) FROM CUPTI_ACTIVITY_KIND_KERNEL WHERE deviceId={gpu}') / 1e6, 3)
        d[f'gpu{gpu}_graph_ms'] = round(one(f'SELECT SUM(end-start) FROM CUPTI_ACTIVITY_KIND_GRAPH_TRACE WHERE deviceId={gpu}') / 1e6, 3)
        for name, pattern in [('tile', 'flash_attn_tile'), ('combine', 'flash_attn_combine')]:
            d[f'gpu{gpu}_{name}_ms'] = round(one(f"SELECT SUM(k.end-k.start) FROM CUPTI_ACTIVITY_KIND_KERNEL k JOIN StringIds s ON k.demangledName=s.id WHERE k.deviceId={gpu} AND s.value LIKE '%{pattern}%'") / 1e6, 3)
        for kind in (1, 2, 8, 10):
            row = db.execute(f'SELECT COUNT(*),SUM(bytes),SUM(end-start) FROM CUPTI_ACTIVITY_KIND_MEMCPY WHERE deviceId={gpu} AND copyKind={kind}').fetchone()
            if row[0]:
                d[f'gpu{gpu}_copykind{kind}'] = {'count': row[0], 'MB': round((row[1] or 0)/1e6,3), 'ms':round((row[2] or 0)/1e6,3)}
    shape = db.execute("SELECT k.gridX,k.gridY,k.gridZ,k.blockX,k.blockY,k.blockZ,k.registersPerThread,k.staticSharedMemory,k.localMemoryPerThread FROM CUPTI_ACTIVITY_KIND_KERNEL k JOIN StringIds s ON k.demangledName=s.id WHERE k.deviceId=1 AND s.value LIKE '%flash_attn_tile%' LIMIT 1").fetchone()
    d['gpu1_tile_shape'] = shape
    out[variant] = d
    db.close()
dest = Path('/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments/model_loading_sequences/qwen35-f16-tile128-20261109/trace_summary.json')
dest.write_text(json.dumps(out, indent=2) + '\n')
print(dest)
