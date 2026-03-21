# bench-daedalmap

LLM chat layer benchmark for DaedalMap. Tests local models (via llama.cpp) on JSON
structure discipline, source grounding, type routing, and catalog discipline.

What the runner does: sends prompts to an OpenAI-compatible chat endpoint, extracts
JSON from the response, scores routing decisions and catalog compliance, emits JSONL
and CSV. No live DaedalMap server or parquet data is required to run any case.

## Files

| File | Purpose |
|---|---|
| `llm_benchmark_v2.json` | 100 test cases across 6 categories (current suite) |
| `llm_benchmark_v1.json` | 100 test cases across 4 categories (legacy reference) |
| `benchmark_catalog.json` | Source of truth for valid source IDs and catalog coverage |
| `benchmark_prompt.py` | Builds the self-contained system prompt with embedded catalog |
| `llm_benchmark_runner.py` | Runner, scorer, and compare tool |
| `validate_suite.py` | Sanity-checks a suite JSON file before running |
| `requirements.txt` | Python dependencies (requests only) |
| `results/` | Runtime output directory (JSONL and CSV, not committed) |

## Setup

```bash
pip install -r requirements.txt
```

## Validate suite before running

```bash
python validate_suite.py llm_benchmark_v2.json
python validate_suite.py llm_benchmark_v1.json
```

Checks: unique case IDs, valid categories, valid expected_types, source IDs against
catalog, requires values from allowed enum, category counts consistent.

## Run a model

Start llama.cpp in OpenAI-compatible server mode, then:

```bash
# Full v2 suite
python llm_benchmark_runner.py --suite llm_benchmark_v2.json --model-tag qwen2.5-7b-q4

# Against a different port
python llm_benchmark_runner.py --suite llm_benchmark_v2.json --model-tag phi3-3.8b --api-base http://localhost:8081

# Quick smoke check (first 10 cases)
python llm_benchmark_runner.py --suite llm_benchmark_v2.json --model-tag test --limit 10

# Single category
python llm_benchmark_runner.py --suite llm_benchmark_v2.json --model-tag test --category json_discipline

# Catalog-only cases (no data annotation, fastest clean run)
python llm_benchmark_runner.py --suite llm_benchmark_v2.json --model-tag test --requires catalog

# With execution validation against hosted API (data_s3 cases)
python llm_benchmark_runner.py --suite llm_benchmark_v2.json --model-tag qwen2.5-7b-q4 \
  --execute --daedalmap-url https://daedalmap.io

# With auth token if needed
python llm_benchmark_runner.py --suite llm_benchmark_v2.json --model-tag qwen2.5-7b-q4 \
  --execute --daedalmap-url https://daedalmap.io --auth-token "<token>"
```

llama.cpp server:

```bash
./llama-server -m qwen2.5-7b-instruct-q4_k_m.gguf --port 8080 -c 4096
```

## --api-base

Points the runner at any OpenAI-compatible chat endpoint. The runner behavior is
identical regardless of endpoint — it scores the LLM's JSON output only.

```bash
# Local llama.cpp (default)
--api-base http://localhost:8080

# Rig inference server
--api-base http://192.168.1.x:8080
```

## requires field (annotation only)

Each case has a `requires` field. Use `--requires` to filter; the runner scores all
cases the same way regardless of this value.

| Value | Meaning |
|---|---|
| `catalog` | LLM routing test only. No external data needed. 75 cases in v2. |
| `data_s3` | LLM routing is scored the same way as catalog cases. When `--execute --daedalmap-url` are set, the runner also POSTs the LLM's order as a `confirmed_order` to the DaedalMap `/chat` endpoint and checks that real records come back. Results in `exec_valid`, `exec_type`, `exec_count` fields. |

## must_not_hallucinate field

Entries are intentional trap keywords, not catalog source IDs. They are strings
the model should never produce in a response. If any appear anywhere in raw output,
the case fails `no_hallucination`.

Examples: `"weather"`, `"stocks"`, `"world_bank"`, `"gdp"`, `"sipri"`, `"fao"`.

This catches:
- Model inventing a plausible-sounding source not in the catalog
- Model confusing a catalog source with an adjacent concept (e.g. returning `owid_co2`
  for a GDP query)

Do not normalize these to catalog source IDs. They are traps by design.

## Suite contract

Required fields on every case:

| Field | Type | Allowed values |
|---|---|---|
| `case_id` | string | Unique across suite. Format: `PREFIX-NNN` |
| `category` | string | `json_discipline`, `type_routing`, `source_grounding`, `catalog_discipline`, `geographic_precision`, `multi_source` |
| `priority` | string | `p0`, `p1`, `p2` |
| `requires` | string | `catalog`, `data_s3` |
| `query` | string | Natural language query sent to model |
| `expected_type` | string | `order`, `navigate`, `disambiguate`, `overlay_toggle`, `clarify`, `chat` |
| `expected_source_ids` | array | Source IDs from catalog. Empty for non-order types. |
| `must_not_hallucinate` | array | Trap keywords. Checked in raw output for all types. |
| `clarify_ok` | bool | If true, `clarify` is accepted alongside `expected_type` |
| `notes` | string | What this case tests |

Source IDs are validated against `benchmark_catalog.json` by the runner and validator.
`expected_source_ids` is only scored when `expected_type` is `order`.

## Categories (v2 - 100 cases)

| Category | Cases | requires | Tests |
|---|---|---|---|
| `json_discipline` | 15 | catalog | Valid JSON, required fields, filter preservation |
| `type_routing` | 20 | catalog | Correct order/clarify/navigate/disambiguate/overlay_toggle/chat |
| `source_grounding` | 20 | catalog | Correct source_id selection, wrong source rejection |
| `catalog_discipline` | 15 | catalog | Graceful refusal, no hallucinated sources |
| `geographic_precision` | 15 | data_s3 | Filters, metrics, year ranges preserved |
| `multi_source` | 15 | data_s3 | Multi-dataset orders, cross-domain queries |

## Categories (v1 - 100 cases)

| Category | Cases | Tests |
|---|---|---|
| `json_discipline` | ~25 | Valid JSON structure |
| `source_grounding` | ~25 | Correct source_id selection |
| `type_routing` | ~25 | order/clarify/navigate routing |
| `catalog_discipline` | ~25 | Refusal and hallucination resistance |

## Scoring

Each case scores PASS / PARTIAL / FAIL:

- **PASS**: valid JSON + correct type + valid source_ids + no hallucination + source hit
- **PARTIAL**: valid JSON + correct type, but missed expected source
- **FAIL**: no JSON, wrong type, hallucinated source, or invalid source_id

Key metrics:

| Metric | Description |
|---|---|
| `json_valid_rate` | Most important for small models - many collapse to prose |
| `type_correct_rate` | Does it route order/clarify/navigate correctly |
| `source_hit_rate` | Does it pick the right source family |
| `no_halluc_rate` | Does it stay inside the catalog |
| `p50 / p95 latency` | Interactive viability on your hardware |

## Compare models

```bash
python llm_benchmark_runner.py --compare results/llm_results_phi3*.jsonl results/llm_results_qwen*.jsonl
```

## Tuning tips

- Lower `--temperature` (0.05-0.1) for more deterministic output from small models
- Increase `--max-tokens` if models truncate mid-JSON (default 400, try 600)
- Run `--category json_discipline` first as a fast screening pass (15 cases)
- Use `--limit 5` for a quick smoke check when setting up a new model
- Qwen3.x think-tag models: pass `--reasoning-budget 0` in llama-server flags
