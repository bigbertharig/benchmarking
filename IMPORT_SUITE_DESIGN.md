# Import Operations Suite Design (bench-importops)

Status: design, not implemented. Written 2026-10-09.

## Purpose

Measure how well a model performs the *current* DaedalMap data import process,
using today's runbook, tools, and validators. Any model can be a contestant:
current cloud models, older checkpoint models via OpenRouter, and local rig
models. Historical import sessions are not the reference; the current process
is.

Process owners (read these, do not restate them here):

- `county-map-private/docs/data_import_operations.md` -- canonical operator
  runbook and gate card (the source of truth for order and stop/go rules)
- `county-map-private/docs/data_pipeline.md` -- source contract and schema meaning
- `county-map-private/build/qa/README.md` -- QA procedure and evidence formats
- `county-map-private/tools/gpu_rig/LOCAL_MODEL_PIPELINE_DECOMPOSITION.md` --
  work-unit pattern and which tasks may be delegated to local models

When those docs change, the suite's case requests and judges follow them; the
suite version bumps (see Versioning). This document defines benchmark scope, not
an alternate import procedure. The runbook controls the exact Gate 0-4 commands
and Geometry MCP call sequence.

## Scope: Gates 0 to 4 only

The runbook's gate card runs 0-8. Gates 0-4 are local preparation that a model
can perform and deterministic validators can judge. Gates 5-8 (human/app QA
evidence, cloud review, release, distribution) stay with the operator, matching
the gpu_rig boundary ("the rig prepares candidates; it never publishes").

| Gate | Model work | Judge (deterministic first) |
| --- | --- | --- |
| 0. Candidate | freeze the candidate: authority, exact release/vintage, licence + redistribution, intended `source_id`/`pack_id`, grain, time model, acquisition durability | required fields present; answer-key fields match (licence id, vintage, grain); must STOP when licence or product identity is unresolved |
| 1. Source contract + geography | decide runtime_primary_file, loc_id format, time, metrics; resolve geography through the Geometry MCP using the runbook's current call sequence and stop rules | crosswalk equals the reference crosswalk produced by the same MCP calls; resolution receipt has the required fields; unresolved/ambiguous artifact present; no silent fallback to names/nearest shape/other vintage; must STOP when the required geometry is not admitted |
| 2. Canonical build | write or patch the converter consuming the MCP crosswalk (no reimplemented resolver); produce parquet, reference.json, metadata via generate_metadata.py, build receipt; follow the physical layout defaults | parquet schema/dtypes; row-count reconciliation vs reference output; duplicate keys at declared grain; loc_id coverage; declared sort order/row-group bounds; rerun produces identical hashes; no converter-level geometry helper use |
| 3. Organize | stable ids, `pack_version: 1.0.0`, runtime_primary_file, source membership, deterministic default_load | `audit_pack_contracts.py --pack-id`; scoped semantic catalog diff shows the pack only where intended |
| 4. Deterministic local QA | run the pack audits and suite; diagnose failures; fix metadata/reference, never weaken a suite | audits + suite pass; suite files byte-identical to the case's copy (weakening = fail) |

## Case families

1. **Gate units** -- one gate per case, starting from a frozen repo + data state
   where the previous gates are already done. This is the work-unit pattern
   ("read small context -> write artifact -> run deterministic command") and
   fits local context by design.
2. **End-to-end** -- Gates 0-4 for one source in one run. Measures planning,
   context management, and compaction; expected to separate models sharply.
3. **Stop traps** -- cases where the right answer is to stop and report:
   unresolved licence, missing geometry spine/vintage, divergent local/cloud
   curated files, sparse local catalog, stale QA receipt. Graded on stopping
   (no forbidden writes) and naming the correct stop condition.
4. **Repair** -- a broken contract (wrong dtype, missing unit, stale
   runtime_primary_file, bad default_load) plus a failing audit; the model must
   fix the source contract, not the suite.

Every case records a reveal level for its request: `symptom` (only the
failure or goal), `pointed` (names the area), or `prescriptive` (says what to
do). Prefer `symptom`.

## Inputs per case

- frozen repo commit (umbrella + public app), worktrees per run
- a sandbox data root: a pinned copy of the needed `county-map-data` subset and
  the raw input files, never the real working mirror
- local loopback Geometry MCP (RUNTIME_MODE=local) at a pinned geometry
  generation, so MCP results are deterministic per case
- context mode, recorded per run:
  - `excerpt`: the runbook gate section plus the specific contract sections
    the gate needs (default)
  - `full_docs`: model must navigate the full docs itself (measures context
    handling; data_pipeline.md alone is ~53k tokens)

## Tools given to the model

- repo tools: list, read (paged, capped), search (capped), replace, write
- Geometry MCP tools (production schemas, local mode)
- wrapped validators and tests (quiet success, located failure): one-line PASS
  with counts, or failure count + first N locations, full log saved to a file
  the model can open
- a data profiler (columns, dtypes, null counts, distinct counts, sample rows)
  instead of raw file reads
- a bounded command allowlist (python on repo scripts, pytest); no network
  except the local MCP; no writes outside the sandbox and worktree

## Metrics per run

- gate pass/fail per judge, and overall
- stop correctness (trap cases)
- edits outside the expected footprint; suite/validator files touched
- MCP usage: tools called, batches, whether a resolver was reimplemented
- turns, wall time, cost, peak context, tool output tokens, compactions
- median TTFT and generation tok/s

## Source selection (first set, to confirm)

Prefer sources that (a) were rebuilt under the current process, (b) have raw
inputs available locally, and (c) cover different geography paths:

- stable identifier source (country codes or FIPS) -> convert_reference path
- coordinate source (points) -> resolve_point path
- a source needing a deeper or newer geometry vintage -> stop-trap variant
- a curated-metric source (many metrics, naming/units/tiers) -> Gate 1/3 metadata

Candidate pool: the packs refreshed in the 2026-10-08/09 staging and
publication prep, the calibration sources from tools/gpu_rig/calibration_runs
(OWID CO2, UN WPP, FEMA disasters, WDI) rebuilt to the current contract, and
NSS shelters (raw input present). Reference outputs are produced by running
the current canonical converter on the frozen raw input.

## Contestants and baselines

- cloud reference: a current cloud coding model through the same harness
- checkpoint models via OpenRouter: openai/gpt-5.4, anthropic/claude-opus-4.6
- open models via OpenRouter, then locally on the rig: qwen/qwen3.8-27b and the
  profiles in `model_task_library.json` `remote_profiles`

## Versioning

The suite version is tied to the runbook revision it encodes. A change to
`data_import_operations.md` gate rules, a judge, a case, the tool set, or the
harness prompt is a new methodology version in `benchmark_methodologies.json`.
Results from different versions are not compared directly.

## Implementation order

1. Freeze one source and its raw input, repo commits, geometry generation,
   reference output, and expected gate receipts.
2. Build the sandbox and deterministic judges for one Gate 0-4 unit case; prove
   the judges detect a changed validator, wrong geography, and an invalid stop.
3. Add the other gate units, stop traps, repairs, then end-to-end cases.
4. Register the suite and methodology only when its runner, fixtures, results,
   and documented smoke command meet [docker/SUITE_CREATION.md](docker/SUITE_CREATION.md).

## Open decisions

1. First 3-5 sources (see Source selection).
2. Where the sandbox data roots and raw fixtures live (shared drive, so the
   rig can run offline).
3. Local Geometry MCP startup for the harness (pinned generation; currently
   not reachable from this desktop session).
4. Whether Gate 0 cases use offline snapshots of upstream pages (needed for an
   offline rig) or are desktop-only.
