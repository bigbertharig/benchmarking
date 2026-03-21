# bench-daedalmap Updates Needed

Scope: this note is only about the benchmark payload itself: test cases, scoring assumptions, catalog alignment, and benchmark documentation. It intentionally ignores Docker packaging and suite integration.

## Status: All resolved - 2026-03-20

All payload and execution-validation issues have been addressed.

## Open Items

None.

## Resolved Items

### 0. `data_s3` validation uses direct bucket check - DONE

Replaced the `/chat` POST approach (which returned 400 Bad Request) with direct R2 bucket
validation via boto3 HeadObject. Runner now checks `published/` then `staging/` (or a
specific prefix via `--s3-prefix`) for each source_id in the LLM's order. Returns
`exec_valid`, `exec_type`, `exec_count`, `exec_error`, `exec_path` fields.

S3 credentials loaded from env vars: `S3_BUCKET`, `S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`. See `.env` for template, `.env.local` for
machine-local credentials. `--daedalmap-url` and `--auth-token` flags removed.

README updated to reflect the boto3 approach and new `--execute` / `--s3-prefix` flags.

### 1. Fix README case counts - DONE

`README.md` now correctly documents both suite files as 100 cases each.

### 2. Clarify what `data_s3` actually means - DONE

`data_s3` cases now have the correct execution-validation path. The runner checks
the public S3/R2 bucket directly using catalog-resolved source paths rather than
posting orders to the DaedalMap `/chat` endpoint.

### 3. Single source of truth for valid source IDs - DONE

Runner now loads `VALID_SOURCE_IDS` from `benchmark_catalog.json` at startup via
`_load_valid_source_ids()`. Hardcoded fallback only fires if the catalog file is missing.
`benchmark_catalog.json` is now the canonical source of truth.

### 4. must_not_hallucinate intent documented - DONE

`README.md` has a dedicated `must_not_hallucinate field` section. Entries are
confirmed as intentional trap keywords (not catalog references). Section explains
both failure modes they catch and states explicitly: do not normalize to catalog IDs.

### 5. README tightened to match actual runner behavior - DONE

"Test modes: local vs cloud" section removed. Replaced with a plain `--api-base`
section that accurately describes it as an endpoint pointer with no behavior change.
`results/` documented as runtime output, not a committed folder.

### 6. Suite contract added - DONE

`README.md` now has a `Suite contract` section with a full table of required fields,
allowed values per field, and scoring semantics for `expected_source_ids`,
`must_not_hallucinate`, and `clarify_ok`.

### 7. Dataset-level sanity checks - DONE

`validate_suite.py` added. Checks: unique case IDs, valid categories, valid
expected_types, source IDs against catalog, requires enum, and prints category counts.
Run with `python validate_suite.py llm_benchmark_v2.json` before accepting suite edits.

## Original Issues (archived)

The original issues tracked in this document have been resolved. Keeping them below
for audit trail only.

---

The original mismatch: README said v2 had 105 cases and v1 had 35. Actual: both 100.

The original data_s3 complaint: runner had no execution validation path. A first pass
was added via `--execute --daedalmap-url`, but live testing showed that validating via
DaedalMap `/chat` was the wrong approach. The final implementation now uses direct
bucket validation.

The original drift risk: three files (runner, prompt, catalog) all hardcoded source IDs
independently. Now runner derives from catalog; benchmark_prompt.py still has its own
inline catalog for the LLM prompt but that is intentional (prompt != scoring).

The original must_not_hallucinate concern: entries like `weather`, `stocks`, `world_bank`
looked like possible mistakes. Confirmed intentional trap terms, documented as such.

The original README overclaims: local/cloud framing, execution validation claims, results/
as committed folder. All corrected.

The original implicit contract: suite structure was only discoverable by reading the runner.
Now explicit in README and enforced by validate_suite.py.
