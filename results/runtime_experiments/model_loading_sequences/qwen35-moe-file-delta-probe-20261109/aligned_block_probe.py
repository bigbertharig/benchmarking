from pathlib import Path
from hashlib import blake2b
import mmap
import json
import time

root = Path('/mnt/shared/experiments/kv-matrix-20261107')
cases = [
    ('short', root / 'qwen35_moe_two_q4_1_16k32k50k_20261109.states', (16384, 32768, 50000)),
    ('long', root / 'qwen35_moe_q41_tile_curve_50k100k150k200k_20261109.states', (50000, 100000, 150000, 200000)),
]
block = 65536
for label, folder, depths in cases:
    for before, after in zip(depths, depths[1:]):
        a = folder / f'worker1_depth{before}.bin'
        b = folder / f'worker1_depth{after}.bin'
        if not a.exists() or not b.exists():
            continue
        start = time.monotonic()
        with a.open('rb') as af, b.open('rb') as bf:
            with mmap.mmap(af.fileno(), 0, access=mmap.ACCESS_READ) as am, mmap.mmap(bf.fileno(), 0, access=mmap.ACCESS_READ) as bm:
                old = {blake2b(am[i:i+block], digest_size=16).digest() for i in range(0,len(am),block)}
                hashes = [blake2b(bm[i:i+block], digest_size=16).digest() for i in range(0,len(bm),block)]
                reused = sum(h in old for h in hashes)
                same_position = sum(am[i:i+block] == bm[i:i+block] for i in range(0,min(len(am),len(bm)),block))
                result = dict(case=label, before=before, after=after, old_bytes=len(am), new_bytes=len(bm),
                              block=block, total_blocks=len(hashes), reused_blocks=reused,
                              same_position_blocks=same_position,
                              delta_payload_upper_bytes=(len(hashes)-reused)*block + len(hashes)*24,
                              analyze_seconds=round(time.monotonic()-start,3))
                print(json.dumps(result), flush=True)
