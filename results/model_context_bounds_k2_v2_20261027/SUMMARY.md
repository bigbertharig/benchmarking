# New model context bounds

Model: `k2-v2-instruct:70b`. Run: `bounds-k2-v2-20261027`.
Manager min/max fits and real load/unload checks; no depth or quality probes.

| Group | GPUs | Min ctx/load s | Max ctx/load s | Status |
|---|---|---:|---:|---|
| compact | 0,1,2,3,4 | 8192 / 229.8 | 13312 / 216.1 | passed |
| ceiling | 0,1,2,3,4,5 | 8192 / 216.6 | 30464 / 213.2 | passed |
