# bench-agent

Executes model-issued tool calls instead of grading tool plans as prose. Each
case runs a bounded OpenAI-compatible tool loop, validates arguments against the
current schema, executes a deterministic local tool, returns the observation to
the model, and scores the final answer.

## Coverage

| Category | Cases | Signals |
| --- | --- | --- |
| Planning | `agent_plan_sequence` | Ordered plan correctness, kept separate from execution |
| Core execution | selection, arguments, execution, observation | Tool choice, semantic arguments, schema validity, execution, observation use |
| Recovery | transient rejection, malformed-interface prompt | Error observation use and successful retry |
| Multi-tool | lookup then conversion | Dependency ordering and observation propagation |
| No-tool | `agent_no_tool_needed` | Avoiding unnecessary calls |
| MCP-style mutation | renamed tool/argument, required field, changed return, ambiguous names | Reliance on current definitions instead of memorized interfaces |

The executable tools are local and deterministic. Artifact operations are
confined to a per-case sandbox. No shell command or external network tool is
exposed to the model.

## Scoring

Execution traces preserve separate component scores:

- `tool_selection`
- `argument_accuracy` when the case declares semantic argument expectations
- `schema_validity`
- `execution_success`
- `observation_interpretation`
- `recovery_success` for recovery cases
- `final_task_success`

Planning cases emit `plan_correctness` and `final_task_success` only. The JSONL
row uses the mean of relevant components as `raw_harness_score` and stores final
task success as `normalized_answer_score`.

## Build

Run on the rig:

```bash
cd /mnt/shared/plans/shoulders/benchmarking/docker/bench-agent
docker build -t bench-agent .
```

## Smoke

Load the model through benchmark mode first, then run:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-agent/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-agent \
  --model qwen3.5:4b \
  --runtime-base http://localhost:11435 \
  --cases agent_tool_select,agent_tool_recovery,agent_no_tool_needed \
  --run-name qwen35_4b_agent_smoke_v1 \
  --hardware-id rig-gpu1-gtx1060-6gb \
  --max-tokens 64 \
  --run-class smoke
```

Run all cases by omitting `--cases`. Use `--limit N` only for harness smoke
runs; label those runs `smoke`. `--max-tokens` defaults to 256 and is recorded
with the result; use 64 for short thermal-safe smoke checks.

## Outputs

```text
/results/bench-agent_<model>_<run-name>/
  summary.json
  <case-id>.json
  sandboxes/<case-id>/
```

Each case trace contains assistant messages, tool calls, argument validation,
execution/error state, final text, and component scores. Endpoint/harness
failures are recorded as schema-v2 failures rather than zero model scores.

## Local Validation

The unit tests run selection, recovery, and no-tool cases through a localhost
mock endpoint and test schema enforcement plus artifact confinement:

```bash
python3 -m unittest tests.test_agent_harness -v
```

This validates the harness protocol, not real-model quality or the Docker image.
