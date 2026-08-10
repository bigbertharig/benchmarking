# Runtime Configuration Matrices

Matrix definitions contain one baseline and an explicit list of profile
overrides. The builder does not produce a Cartesian product. Each resolved
profile gets a stable configuration hash and becomes one unified-campaign
block.

Measured runtime-capacity experiments live separately in
`results/runtime_experiments/`. They are not quality-score records and do not
replace historical model graphs or score ledger entries.

Generate the Qwen3.5 4B structured-worker campaign:

```bash
python3 build_runtime_matrix_campaign.py \
  runtime_matrices/qwen35_4b_structured_worker_matrix.json \
  --output campaigns/qwen35_4b_structured_worker_matrix.json
```

Validate the schedule on the rig before execution:

```bash
python3 /mnt/shared/scripts/benchmarks/run_campaign.py \
  /mnt/shared/plans/shoulders/benchmarking/campaigns/qwen35_4b_structured_worker_matrix.json \
  --dry-run
```

Profiles are dependency-chained. This prevents the scheduler from spreading
variants across different single-worker GPUs and keeps the comparison on the
first available slot. The manifest records request settings, context size, KV
cache type, chat template, and the exact runtime argument list. Result rows
carry the same configuration body and its canonical hash.

The included matrix is provisional and intentionally limited to the strict
JSON worker task. It compares the normal profile with the structured sampling
candidate and controlled thinking, grammar, context, KV cache, chat-template,
system-prompt, and stop-sequence changes. Promote a configuration only after a
larger validated campaign.
