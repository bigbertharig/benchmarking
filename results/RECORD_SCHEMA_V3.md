# Benchmark Record Schema v3

Schema v3 adds explicit benchmark methodology identity without rewriting or
invalidating schema-v2 and legacy rows. The append-only JSONL ledger remains
the authority; Markdown, graph data, scoreboards, Pareto output, and
methodology history are derived views.

Every new record contains the schema-v2 identity, evidence, quality, runtime,
efficiency, and failure fields plus:

```json
{
  "methodology": {
    "id": "bench-code/evalplus",
    "version": "2.0.0",
    "comparison_group": "evalplus-0.3-plus-v1"
  }
}
```

- `id` identifies the maintained test method.
- `version` changes when the harness implementation changes.
- `comparison_group` changes when scores stop being directly comparable due
  to dataset, prompt, extraction, grading, or score-definition changes.

The active registry is `benchmark_methodologies.json`. Historical records
without these fields are exposed as `legacy-unversioned` by readers but are
not modified on disk.

The primary model scoreboard remains unchanged for graph continuity. Generate
the parallel methodology-aware history with:

```bash
python3 build_methodology_history.py
```

That output selects evidence only within the same model, test, methodology,
and comparison group. This lets an older result remain visible beside a newer
method instead of treating either as invalid.
