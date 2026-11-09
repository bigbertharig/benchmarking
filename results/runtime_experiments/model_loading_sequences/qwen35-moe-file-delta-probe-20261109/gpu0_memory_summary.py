from pathlib import Path
import csv
from collections import Counter

p=Path('/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_q41_tile_curve_50k100k150k200k_20261109.gpu.csv')
counts=Counter()
with p.open(newline='') as f:
    for row in csv.reader(f):
        if len(row)>2 and row[1].strip()=='0':
            try: counts[int(row[2].strip().split()[0])]+=1
            except ValueError: pass
print('samples',sum(counts.values()),'min',min(counts),'max',max(counts))
print('common',counts.most_common(12))
for threshold in (21000,22000,22500,23000):
    print('at_or_above',threshold,sum(v for m,v in counts.items() if m>=threshold))
