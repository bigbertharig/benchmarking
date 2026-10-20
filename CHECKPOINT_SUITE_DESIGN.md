# Checkpoint Suite Design (bench-checkpoint)

Status: design, not implemented. Written 2026-10-09.

## Purpose

Measure local models against a fixed, personal capability checkpoint instead of
a moving frontier. The checkpoint is the cloud coding era that first produced
real, accepted work in these repos: OpenAI Codex `gpt-5.4` (and `gpt-5.3-codex`)
and Claude Opus 4.6, roughly Feb to Jul 2026.

A local model "reaches the checkpoint" when it completes the same real tasks,
from the same starting repo state, to the same acceptance standard, through the
same harness. The suite answers "can it do the work that was actually done
here", not a public leaderboard question.

## Source material (inventoried 2026-10-09)

| Machine | Source | What survives | Checkpoint-era content |
| --- | --- | --- | --- |
| Desktop | `~/.codex/sessions`, `archived_sessions` | full transcripts, 960 sessions from 2026-03-03 | 117 sessions with gpt-5.4 / gpt-5.3-codex (Mar 3 to Jul 1), 107 edited files |
| Pi | `~/.codex/sessions` | full transcripts, 66 sessions from 2026-02-12 | 27 gpt-5.4 + 30 gpt-5.3-codex (Feb to Apr) |
| Pi | `~/.claude/history.jsonl` | prompts only, 2043 prompts | Feb 584, Mar 908 (Opus 4.6 era); no responses |
| Desktop | `~/.claude/history.jsonl` | prompts only, 97 prompts | Dec 2025 to Mar 2026 |
| Desktop | VS Code chatSessions | Copilot gpt-4.1 / gpt-5-mini, Oct to Nov 2025 | pre-checkpoint, not used |

Claude Code full transcripts older than 30 days were auto-deleted on both
machines. `cleanupPeriodDays` is now 3650 on both, so the loss stops here.
Opus 4.6 tasks can still be recovered as (prompt + git outcome) without the
model transcript.

Projects represented: `global map` (county-map public + county-map-private),
`webtest` (site), `disaster-clippy`, and Pi-side `llm_orchestration` work.

## Unit of a case

Sessions are long working sessions (tens of prompts, some 200 to 400), so a
session is not a case. A case is one bounded slice:

- `request`: the user prompt (or short prompt sequence) that asked for the work
- `base`: repo state before the work (git commit)
- `accepted`: the change that was kept (git commit), the ground-truth outcome
- `grader`: how a candidate result is judged (see families)

Anchoring rule: for each checkpoint session, find commits in the touched repos
whose time falls inside the session window and whose changed files overlap the
files the session edited. Each matching commit, with its parent as `base` and
the prompts between the previous commit and this one as `request`, is a
candidate. Committed changes are the "accepted outcome" signal; uncommitted
work is not a case.

## Task families and grading

| Family | Examples from the inventory | Grader | Signal strength |
| --- | --- | --- | --- |
| Bug fix | pack loading drift, stuck explore-mode animation, admin account page error, pack data path fixes | tests present at `accepted` (or added from it) run against the candidate change | strong |
| Data / QA | pack QA after publish, aggregate rebuild verification, source import fixes | existing QA validators (county-map-private build/qa) plus artifact checks | strong |
| Small feature / site edit | basic site updates, landing page changes | file-level checks, rendered page checks, rubric | medium |
| Review / plan check | fresh-eyes doc reviews, plan double-checks, security reviews | rubric built from findings the checkpoint model produced and that were acted on | weak, keep under about 20 percent of cases |
| Repo ops | git pull / merge conflict help | scripted repo with known conflicts, final tree must match | strong but narrow |

The harness records observations; it does not decide acceptability (matches
SUITE_CREATION.md section 4). Pass/partial thresholds live in analysis.

## Case schema (draft)

```json
{
  "case_id": "CKPT-BUG-001",
  "family": "bug_fix",
  "source": {"tool": "codex", "model": "gpt-5.4", "session_date": "2026-04-24"},
  "repo": "county-map",
  "base_commit": "<sha>",
  "accepted_commit": "<sha>",
  "request": "<anonymized prompt text>",
  "context_files": ["<repo-relative paths the request pointed at>"],
  "grader": {"type": "pytest", "targets": ["tests/test_x.py::test_y"]},
  "time_budget_s": 1800,
  "notes": "what the case tests"
}
```

## Anonymization

The benchmarking repo is public, so cases are anonymized before they land here:

- strip names, emails, wallet addresses, hostnames, IPs, tokens, and paths under
  user home dirs (normalize to repo-relative paths)
- prompts keep intent and constraints, lose personal and business detail
- never copy `.env` files, credentials, or raw session transcripts into the
  repo; the raw inventory stays local to the machine it came from
- repo snapshots are referenced by commit, not vendored; the runner checks out
  `base_commit` from a local mirror at run time

## Runner (campaign-v1)

Proposed registry entry in `docker/suite_contracts.json`:

- `runtime_mode`: `external` (campaign runner owns model loading)
- `limit_supported`: true
- `task_selector`: `--cases`
- `profile_policy`: `fixed_case_prompt` (each case owns its request; the agent
  system prompt is part of the methodology version)
- `hardware_id_required`: true (speed is part of the result)

Execution per case:

1. Create a throwaway worktree at `base_commit` inside the container (no
   network; repo mirror mounted read-only).
2. Run an agent loop against the model with repo tools: read file, search,
   edit (str_replace style), and a bounded command allowlist (tests, linters,
   validators). Reuse the bench-agent tool-loop code and add repo tools, rather
   than writing a second loop.
3. Stop on finish, token budget, or time budget.
4. Run the case grader on the worktree; store the diff, trace, and grader output.
5. Write `/results/bench-checkpoint_<model_safe>_<run_name>/<case_id>.json`.

Metrics per case: `grader_pass`, `partial` (for example some tests pass),
`turns`, `prompt_tokens`, `gen_tokens`, `wall_s`, `edits_outside_scope`.

Results depend on the harness as much as the model. The agent loop and its
prompt are versioned in `benchmark_methodologies.json`; changing either starts a
new comparison group. Harness research lives in the llm-gateway repo under
`docs/harness/`.

## Calibration

- Reference outcome: the `accepted_commit` (what the checkpoint model plus the
  operator produced).
- Checkpoint baseline (do this early, before the models are retired): run the
  original checkpoint models through the same harness via OpenRouter on the
  same cases. Their scores become the line local models must reach, and they
  separate "the harness is the bottleneck" from "the model is the bottleneck".
  Available on OpenRouter as of 2026-10-09 (price per 1M tokens in/out):

  | Checkpoint | OpenRouter id | Context | Price |
  | --- | --- | --- | --- |
  | Codex 5.4 | `openai/gpt-5.4` (also `:batch`) | 1.05M | 2.50 / 15 |
  | Codex 5.3 | `openai/gpt-5.3-codex` | 400k | 1.75 / 14 |
  | Opus 4.6 | `anthropic/claude-opus-4.6` (also `:batch`) | 1M | 5 / 25 |
  | Sonnet 4.6 | `anthropic/claude-sonnet-4.6` (also `:batch`) | 1M | 3 / 15 |

  `:batch` variants are half price and suit overnight runs. Use a dedicated
  key with a credit limit.
- Local runs: profiles from `model_task_library.json` `remote_profiles`
  (for example chat-27b at 65k ctx), plus candidates as they are benchmarked.

## Build plan

1. Mining script: session inventory, then commit anchoring, then a candidate
   list (date, repo, family guess, files, base/accepted shas). Runs on each
   machine against its own history; outputs stay local.
2. Pick 20 to 30 candidates, balanced across families.
3. For each picked case: anonymize the request, confirm the grader, freeze
   `base`.
4. Implement bench-checkpoint per SUITE_CREATION.md (contract, CLI, outputs,
   methodology, README plus BENCH_CHECKPOINT_HISTORY.md, validation).
5. Smoke: one case with `--limit 1`, first a cloud model via OpenRouter to
   validate the harness, then chat-27b.

## Open questions

- Repo mirrors: where the runner reads county-map / county-map-private history
  from on an offline rig (a mirror on the shared drive is the default proposal).
- Opus 4.6 prompt-only tasks: include them (prompt plus commit outcome), or keep
  the first version Codex-only where the transcript confirms the model.
- Time budget per case on local hardware (chat-27b prompt processing is about
  45 to 50 seconds per 20k tokens; long agent loops will be slow).
