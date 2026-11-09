#!/usr/bin/env python3
"""Summarize six decode-only Nsight SQLite traces and their generation logs."""
import json
import re
import sqlite3
from pathlib import Path

raw = Path('/mnt/shared/experiments/kv-matrix-20261107')
name = 'qwen35_moe_q41_decode_trace_16k32k50k_20261109'
out = Path('/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments/model_loading_sequences/qwen35-moe-q41-decode-trace-16k32k50k-20261109/trace_summary.json')
summary = {'campaign': name, 'capture': 'cudaProfilerStart/Stop around 64-token worker generation', 'stages': {}}
for depth in ('16k', '32k', '50k'):
    for variant in ('fallback', 'native'):
        stage = f'{variant}_{depth}'
        stem = raw / f'{name}_{stage}'
        log = stem.with_suffix('.log').read_text()
        match = re.search(r'GEN_METRIC phase=\S+ name=worker used=(\d+) tokens=(\d+) seconds=([\d.]+) tps=([\d.]+)', log)
        assert match and int(match.group(2)) == 64
        assert 'GEN_AGGREGATE' in log and 'ok=1' in log
        conn = sqlite3.connect(str(stem) + '.sqlite')
        q = lambda sql: conn.execute(sql).fetchone()[0] or 0
        ns_to_ms = lambda n: round(n / 1e6, 3)
        kernel_join = 'CUPTI_ACTIVITY_KIND_KERNEL k JOIN StringIds s ON k.demangledName=s.id'
        kernels = {
            'gpu0_total_ms': ns_to_ms(q('SELECT SUM(end-start) FROM CUPTI_ACTIVITY_KIND_KERNEL WHERE deviceId=0')),
            'gpu1_total_ms': ns_to_ms(q('SELECT SUM(end-start) FROM CUPTI_ACTIVITY_KIND_KERNEL WHERE deviceId=1')),
            'gpu1_attention_ms': ns_to_ms(q(f"SELECT SUM(k.end-k.start) FROM {kernel_join} WHERE k.deviceId=1 AND s.value LIKE '%flash_attn_ext_vec%'")),
            'gpu1_q41_dequant_ms': ns_to_ms(q(f"SELECT SUM(k.end-k.start) FROM {kernel_join} WHERE k.deviceId=1 AND s.value LIKE '%dequantize_block_q4_1%'")),
            'gpu0_graph_ms': ns_to_ms(q('SELECT SUM(end-start) FROM CUPTI_ACTIVITY_KIND_GRAPH_TRACE WHERE deviceId=0')),
        }
        copies = {}
        for direction, kind in [('host_to_1060', 1), ('1060_to_host', 2)]:
            row = conn.execute('SELECT count(*),SUM(bytes),SUM(end-start) FROM CUPTI_ACTIVITY_KIND_MEMCPY WHERE deviceId=1 AND copyKind=?', (kind,)).fetchone()
            copies[direction] = {'instances': row[0], 'MB': round((row[1] or 0) / 1e6, 3), 'time_ms': ns_to_ms(row[2] or 0)}
        shape = conn.execute(f'''SELECT k.gridX,k.gridY,k.gridZ,k.blockX,k.blockY,k.blockZ,k.registersPerThread,k.staticSharedMemory,k.localMemoryPerThread
            FROM {kernel_join} WHERE k.deviceId=1 AND s.value LIKE '%flash_attn_ext_vec%' LIMIT 1''').fetchone()
        summary['stages'][stage] = {
            'occupied_after_generation': int(match.group(1)), 'tokens': 64,
            'decode_seconds': float(match.group(3)), 'decode_tps': float(match.group(4)),
            'q41_fallback_warning': 'no FlashAttention vector kernel compiled' in log,
            'kernels': kernels, 'copies': copies,
            'attention_shape': dict(zip(('grid_x','grid_y','grid_z','block_x','block_y','block_z','registers_per_thread','static_shared_bytes','local_bytes_per_thread'), shape)),
        }
        conn.close()
out.write_text(json.dumps(summary, indent=2) + '\n')
