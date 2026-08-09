# Model Pareto Frontier

Generate the machine-readable frontier from the canonical JSONL ledger:

```bash
python3 build_pareto_frontier.py
```

Output: `results/model_pareto_frontier.json`

The builder maximizes measured quality and reliability while minimizing
wall-clock time, TTFT, peak VRAM, GPU-seconds, and energy. It compares records
only when they expose the same cost dimensions. Missing measurements are never
inferred from model size, placement, or prose notes.

Cost-bearing records also require an explicit `hardware_id`; hardware-ambiguous
latency or GPU measurements remain in the ledger but are excluded from Pareto
competition.

Legacy records do not contain schema-v2 efficiency fields and are reported in
diagnostics but excluded from frontier candidates. This makes the initially
empty frontier an explicit measurement backlog rather than a fabricated model
ranking.
