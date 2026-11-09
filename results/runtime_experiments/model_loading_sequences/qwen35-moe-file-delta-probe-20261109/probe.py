from pathlib import Path
import subprocess
import time
import hashlib
import json

root = Path('/mnt/shared/experiments/kv-matrix-20261107')
receipt_dir = Path('/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments/model_loading_sequences/qwen35-moe-file-delta-probe-20261109')
receipt_dir.mkdir(exist_ok=True)
scratch = Path('/data/bench-staging/delta-probe-20261109')
scratch.mkdir(exist_ok=True)
results = []
cases = (
    (root / 'qwen35_moe_two_q4_1_16k32k50k_20261109.states',1,16384,32768),
    (root / 'qwen35_moe_two_q4_1_16k32k50k_20261109.states',1,32768,50000),
    (root / 'qwen35_moe_two_q4_1_16k32k50k_20261109.states',2,32768,50000),
    (root / 'qwen35_moe_q41_tile_curve_50k100k150k200k_20261109.states',1,50000,100000),
    (root / 'qwen35_moe_q41_tile_curve_50k100k150k200k_20261109.states',2,50000,100000),
)
for folder, worker, old_depth, new_depth in cases:
    old = folder / f'worker{worker}_depth{old_depth}.bin'
    new = folder / f'worker{worker}_depth{new_depth}.bin'
    compressed = scratch / f'full_{worker}_{new_depth}.zst'
    patch = scratch / f'delta_{worker}_{old_depth}_{new_depth}.zst'
    output = scratch / f'reconstructed_{worker}_{new_depth}.bin'
    commands = (
        ('full_encode', ['zstd','-q','-1','-T1','-f',str(new),'-o',str(compressed)]),
        ('delta_encode',['zstd','-q','-1','-T1','-f',f'--patch-from={old}',str(new),'-o',str(patch)]),
        ('delta_decode',['zstd','-q','-d','-f','--long=30',f'--patch-from={old}',str(patch),'-o',str(output)]),
    )
    timing = {}
    for phase, cmd in commands:
        t = time.monotonic()
        subprocess.run(cmd, check=True)
        timing[phase] = round(time.monotonic()-t,3)
    def sha(path):
        h = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(4*1024*1024),b''):
                h.update(chunk)
        return h.hexdigest()
    exact = sha(new) == sha(output)
    result = dict(worker=worker,old_depth=old_depth,new_depth=new_depth,old_bytes=old.stat().st_size,
                  full_bytes=new.stat().st_size,compressed_full_bytes=compressed.stat().st_size,
                  patch_bytes=patch.stat().st_size,exact_reconstruction=exact,**timing)
    results.append(result)
    print(json.dumps(result),flush=True)
    output.unlink()
    compressed.unlink()
    patch.unlink()
    if not exact:
        raise RuntimeError('reconstruction mismatch')
(receipt_dir / 'receipt.json').write_text(json.dumps({'status':'passed','codec':'zstd --patch-from -1','cases':results},indent=2)+'\n')
