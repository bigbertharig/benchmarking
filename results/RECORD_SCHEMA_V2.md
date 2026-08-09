# Benchmark Record Schema v2

`results/model_benchmark_records.jsonl` is the canonical benchmark result source.
Markdown reports and scoreboard JSON are derived artifacts and must never be
edited as primary data.

Schema v2 remains supported for historical records. New writes use schema v3;
see `RECORD_SCHEMA_V3.md` for methodology versioning.

Every new line is a JSON object with `schema_version: 2` and these field groups:

- identity: `run_id`, `run_at`, `model`, `test_id`, `harness`, `suite`
- evidence: `status`, `run_class`, `sample_count`, `metric`
- quality: `score`, `score_pct`, `raw_harness_score`,
  `normalized_answer_score`, `format_compatibility`,
  `extractor_failure_count`
- runtime: `runtime_id`, image, configuration ID/hash/body, and hardware ID
- efficiency: prompt/generation throughput, TTFT, wall time, VRAM, KV cache,
  GPU-seconds, energy, timeouts, and failed requests
- failure: machine-readable kind and human-readable message

Allowed `run_class` values are `smoke`, `provisional`, `validated`, and `full`.
The loader labels pre-v2 rows as `legacy` without guessing their sample quality.

Selection is deterministic. It prefers run class, then sample count, format
compatibility, timestamp, and run ID. Failures are retained but never selected
as a best score. This prevents a later smoke run from replacing validated or
full evidence.

Ledger reads and appends use a shared file lock. Recorder calls also serialize
the append-and-refresh pipeline, and derived JSON/Markdown files are replaced
atomically. Generators reject invalid JSON, duplicate run IDs, and empty
selected result sets before touching existing outputs.

Record a failure explicitly:

```bash
python3 record_benchmark_result.py \
  --model qwen3.6:27b \
  --test-id bbh \
  --status failure \
  --run-class smoke \
  --harness bench-reasoning \
  --suite qwen36_bbh_smoke \
  --methodology-id bench-reasoning/lm-eval-normalized \
  --methodology-version 2.0.0 \
  --comparison-group lm-eval-0.4.11-reasoning-extract-v2 \
  --failure-kind timeout \
  --failure-message "request exceeded 600 seconds" \
  --timeout-count 1
```

Regenerate derived artifacts:

```bash
python3 build_benchmark_reference.py
python3 build_model_library_scoreboard.py
```

Both generators fail instead of overwriting their outputs with empty data.
