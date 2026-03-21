# bench-daedalmap Updates Needed

Scope: this note is only about the benchmark payload itself: test cases, scoring assumptions, catalog alignment, and benchmark documentation. It intentionally ignores Docker packaging and suite integration.

## Status: All resolved - 2026-03-20

All items below were addressed. See `README.md` for current state of each area.

## Resolved Items

### 1. Fix README case counts - DONE

`README.md` now correctly documents both suite files as 100 cases each.

### 2. Clarify what `data_s3` actually means - DONE

`data_s3` cases now have real execution validation. The runner supports
`--execute --daedalmap-url` flags that POST the LLM's confirmed order to the
DaedalMap `/chat` endpoint and check that real records come back.
`exec_valid`, `exec_type`, `exec_count`, `exec_error` fields appear in all output rows.
See the `requires field` and run examples sections of `README.md`.

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

The original data_s3 complaint: runner had no execution validation path. Now it does
via `--execute --daedalmap-url`. Bucket is public so no auth required for standard sources.

The original drift risk: three files (runner, prompt, catalog) all hardcoded source IDs
independently. Now runner derives from catalog; benchmark_prompt.py still has its own
inline catalog for the LLM prompt but that is intentional (prompt != scoring).

The original must_not_hallucinate concern: entries like `weather`, `stocks`, `world_bank`
looked like possible mistakes. Confirmed intentional trap terms, documented as such.

The original README overclaims: local/cloud framing, execution validation claims, results/
as committed folder. All corrected.

The original implicit contract: suite structure was only discoverable by reading the runner.
Now explicit in README and enforced by validate_suite.py.
