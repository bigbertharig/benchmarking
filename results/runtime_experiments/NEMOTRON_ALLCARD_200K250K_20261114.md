# Nemotron 3.5 Bolt 74B: all-card 200K and 250K occupied context (2026-11-14)

The registered [capacity runner](../../scripts/integration/capacity_run.py) loaded NVIDIA-Nemotron-3.5-Bolt-74B-A9B-UD-Q3_K_XL across all six currently installed GPUs: one RTX 3090 Ti, one GTX 1070, and four GTX 1060s. It reserved the model's 262,144-token context. The manager planned a 46,8,16,7,8,4 layer split in PCI bus order, with the 1070 receiving 16 layers. The run used the existing default profile and micro-batch 64. The [JSON receipt](nemotron_allcard_200k250k_20261114.json) records card UUIDs, actual token counts, times, power, and recall.

| Occupied prompt | Prefill | Time to first token | 160-token decode | Code recall |
| ---: | ---: | ---: | ---: | :---: |
| 200,543 tokens | 136.42 tok/s | 1,470.0 s | 10.04 tok/s | passed |
| 249,889 tokens | 124.14 tok/s | 2,013.0 s | 8.79 tok/s | passed |

The model load took 200.0 s and a short prompt decoded at 20.82 tok/s. Moving from about 200K to 250K occupied context reduced decode speed by 12.5%. The full 250K request took 2,031.6 s, including prefill and output. Both depth prompts were independent synthetic documents with a code near the start; prompt caching was off and the runner forced 160 output tokens. Recall passed, but the generated answer included extra text, so this is a capacity and speed check rather than a strict one-word answer quality result.

The older [all-1060 251K receipt](../context_capacity_validated_depth_20261026/receipts/nemotron-3_5-bolt_74b-a9b__trained_ceiling.json) measured 8.11 tok/s at 251,308 occupied tokens. Today's mixed-card layout measured 8.79 tok/s at 249,889, an 8.4% higher decode rate. The layer split changed (old 47,8,12,9,7,6; new 46,8,16,7,8,4), so this compares complete placements rather than isolating the 1070's effect. Both tests used the same model ID and 262K reservation. The new run exited successfully and unloaded the benchmark model.

The first attempt never loaded because the rig could not SSH back to the Pi manager: the Pi's wired firewall allowed NFS but not SSH from 10.0.0.3. A temporary SSH rule limited to that wired source was added for the successful second attempt and removed after the run. The first attempt's Manager record is a failed start, not benchmark evidence.
