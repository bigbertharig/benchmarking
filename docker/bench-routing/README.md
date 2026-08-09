# bench-routing

Measures whether a model chooses the cheapest execution tier that can still
complete a task. The tier list and approximate cost units are explicit in
`routing_cases.json`; the runner has no model-specific hidden defaults.

## Score

For each case:

```text
task_success = 1 when selected capability >= required capability
routing_efficiency = cheapest sufficient cost / selected capable cost
routing_value = task_success * routing_efficiency
```

Under-capacity routes score zero. Over-provisioned routes can succeed but lose
efficiency. Cases involving unknown destructive authorization or hardware danger
require `human_escalation`; selecting a brain model does not count as success.

The model must return strict JSON:

```json
{"route": "single_worker", "reason": "short reason"}
```

The schema-v2 row stores mean routing value as `score`, mean routing efficiency
as `raw_harness_score`, and mean task success as `normalized_answer_score`.

## Build And Run

```bash
cd /mnt/shared/plans/shoulders/benchmarking/docker/bench-routing
docker build -t bench-routing .

docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-routing/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-routing \
  --model qwen3.5:4b \
  --runtime-base http://localhost:11435 \
  --run-name qwen35_4b_routing_v1 \
  --run-class validated
```

Use `--limit 2 --run-class smoke` for a short harness/model-format check.

## Pareto Output

Routing value measures orchestration choices. Measured model/runtime tradeoffs
are a separate derived output:

```bash
python3 build_pareto_frontier.py
```

See [PARETO_FRONTIER.md](../../results/PARETO_FRONTIER.md). The builder never
substitutes tier cost units for measured latency, VRAM, GPU-seconds, or energy.

## Local Validation

```bash
python3 -m unittest tests.test_routing_pareto -v
```

This covers routing math, human escalation, Pareto dominance, and a localhost
mock-endpoint CLI smoke. It does not represent a real-model run.
