# bench-checkpoint desktop prototype

This directory holds a **v0 desktop prototype**, not a registered Docker or
campaign suite. The [campaign design](../../CHECKPOINT_SUITE_DESIGN.md) defines
the target methodology; [history](BENCH_CHECKPOINT_HISTORY.md) records prototype
runs and known gaps. The current case is [CKPT-SEC-001](cases/CKPT-SEC-001.json).

## Local setup

1. Use Python with `pytest` installed and local git mirrors containing each
   case's `base_commit` and `accepted_commit`.
2. Copy `repos.example.json` to ignored `repos.local.json` and set local mirror
   paths. Copy `.env.example` to ignored `.env` and set `OPENROUTER_API_KEY` for
   OpenRouter runs. A local endpoint may use `--no-key` and `--base-url`.
3. Run `python run_case.py --case cases/CKPT-SEC-001.json --model MODEL_ID`.
   Use `python run_case.py --help` for the other options. `ckpt_smoke.py` is a
   separate synthetic tool-loop probe.

The runner creates a temporary worktree, applies the case's accepted hidden
tests after the model stops, and writes a JSON result under ignored `results/`.
Keep `.env`, `repos.local.json`, worktree artifacts, and results local. Review
any case prompt and commit references before sharing a new case.

## Current limits and next work

- This is a research prototype with one case. Results are exploratory and must
  not be compared with campaign suite scores.
- The prototype does not isolate the model's repository tools in a container;
  run only against trusted case files and disposable local mirrors.
- Grading currently records edits outside the expected footprint but does not
  fail solely on those edits. Harden path and grader boundaries before treating
  passes as campaign evidence.
- Build the campaign runner, contract, methodology entry, frozen cases, and
  deterministic validation described in the
  [suite creation guide](../SUITE_CREATION.md). Register the suite only then.
