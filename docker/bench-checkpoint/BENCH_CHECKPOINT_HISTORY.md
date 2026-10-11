# bench-checkpoint history

Methodology changes and run notes. Design: `../../CHECKPOINT_SUITE_DESIGN.md`.

## Methodology versions

### v0-prototype (2026-10-09)

- Runner: `run_case.py`, one case, one model, one run, from the desktop against
  OpenRouter. Not campaign-v1 yet (no `suite_contracts.json` entry, no Docker).
- Worktree at `base_commit`; tools: list_dir, read_file (400-line pages),
  search (git grep, 80 matches), replace_in_file, write_file, run_tests
  (pytest, tests/ only). Tool output capped at 6,000 chars.
- Fixed system prompt (in `run_case.py`); request from the case file.
- Grader: the accepted commit's hidden test files are dropped into the worktree
  after the run, then the grader targets are run with pytest.
- Streaming with usage; per-turn TTFT, generation time, prompt/completion
  tokens, cached tokens, cost.
- No prompt caching hints (no Anthropic cache_control).
- Network retries added after the first Qwen run (3 attempts, 5s/10s backoff).

## Runs

| Date | Case | Model | Pass | Turns | Wall | Cost | Peak ctx | Gen tok/s | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-09 | smoke (synthetic) | openai/gpt-5.4 | yes | 5 | 9s | $0.019 | 5k total | - | `ckpt_smoke.py` |
| 2026-10-09 | smoke (synthetic) | anthropic/claude-opus-4.6 | yes | 4 | 10s | $0.047 | 7k total | - | `ckpt_smoke.py` |
| 2026-10-09 | CKPT-SEC-001 | openai/gpt-5.4 | yes | 9 | 24s | $0.053 | 6,174 | ~108 | edited data_loading.py + own test |
| 2026-10-09 | CKPT-SEC-001 | anthropic/claude-opus-4.6 | yes | 16 | 71s | $0.998 | 21,223 | ~105 | wider exploration; no caching so cost is high |
| 2026-10-09 | CKPT-SEC-001 | qwen/qwen3.8-27b | void | 26 | 712s | $0.037 | 40,696 | ~37 | provider dropped connection at turn 26; state at cut failed 1/5 hidden tests; rerun with retries |
| 2026-10-09 | CKPT-SEC-001 | qwen/qwen3.8-27b | void | 24 | 539s | $0.030 | 36,638 | - | rerun: dropped again at turn 25 (3 retries failed); TTFT rose to 65s before the drop; same 1/5 hidden test failing at cut. Next: pin a different provider via OpenRouter provider routing and record the serving provider |

## Notes

- CKPT-SEC-001's request was rebuilt from the accepted change and names the
  leaking field, so it tests the fix more than the discovery. Add a reveal
  level to the case schema (symptom / pointed / prescriptive).
- Harness lessons from these runs are kept in the llm-gateway repo:
  `docs/harness/lessons_bench_checkpoint.md`.
