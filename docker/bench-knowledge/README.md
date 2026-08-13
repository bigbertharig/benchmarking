# bench-knowledge

Runs a frozen, generation-scored multiple-choice probe against the campaign's
shared OpenAI-compatible runtime. It measures basic academic, science,
commonsense, misconception-resistance, and reading behavior without depending
on llama.cpp completion logprob response internals.

This is methodology `bench-knowledge/chat-mc` version `3.0.0`. It is not
directly comparable with historical `lm-eval-gguf` results.

## Tasks

- `academic`
- `science`
- `commonsense`
- `truthfulness`
- `reading`

Legacy task names `mmlu`, `arc_challenge`, `hellaswag`, `truthfulqa_mc2`, and
`boolq` are accepted as aliases, but results are recorded under explicit
`knowledge_<task>_probe_v1` IDs. They are not official benchmark dataset scores.

## Campaign Use

```json
{
  "id": "model_knowledge",
  "model": "model-id",
  "gguf": "/mnt/shared/models/model/model.gguf",
  "placement": "brain",
  "suite": "bench-knowledge",
  "suite_args": ["--tasks", "academic,science,commonsense,truthfulness,reading"],
  "limit": 5,
  "run_class": "smoke"
}
```

The suite accepts the common campaign flags plus `--tasks`, `--limit`,
`--tuning-profiles`, `--cases-file`, and `--timeout`. It requires a uniquely
resolved model profile with a `system_prompt`.

## Output and Resume

Artifacts are written to:

```text
/results/bench-knowledge_<model_safe>_<run_name>/
```

`status.json` tracks task-level completion. Reusing the run name skips completed
tasks. Each task writes its parsed answer trace to `<task>.json`, and canonical
result rows go to the shared records ledger.

## Historical Backend

Version 2 used an internal llama.cpp server and lm-eval loglikelihood requests.
Modern llama.cpp no longer provides the completion echo/logprob response shape
that adapter expected. That method is retained as `retired` in the methodology
registry and its existing artifacts remain historical evidence.
