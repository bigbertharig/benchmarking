# Named model mode smoke series — 2026-11-11

This series checks the HTTP serving versions of three model/mode pairs. The
request key is the canonical registry model ID and `single-chat-fast`; the
executable placement lives in orchestration
[`model_modes.py`](https://github.com/bigbertharig/llm_orchestration/blob/main/shared/scripts/rig/model_modes.py).
The gateway and harness should consume a ready route after orchestration loads
the requested pair. These experimental modes are not yet ordinary gateway
offers.

The [series manifest](series.json) runs through the existing sequence runner.
It first waits for the Coder smoke already running on port 11522, checks all
three Phase 4 stage exits, then loads Nemotron and Qwen3.6 35B in turn. Each
load uses its named orchestration mode and is followed by the same Phase 4
smoke. The wrapper logs are under `/mnt/shared/logs/benchmarks/placement_*.log`;
the sequence receipt and per-stage logs are under
`results/runtime_experiments/model_loading_sequences/model_mode_smokes_20261111_v2/`.
The Manager job is `model_mode_smokes_20261111_v2`, and the all-card claim is
`model-mode-smokes-v2-20261111`. The first queue was stopped before any model
switch to correct the 35B registry ID from the older Q4_K_M entry to the active
Q4_K_XL entry. A successful final stage leaves the 35B mode
loaded. The claim must be reviewed and released when the sequence ends.

## Comparison context

Previous Phase 4 smoke wall times, excluding cold load, were 41m34s for the
older 35B Q4_K_M quant,
74m33s for Nemotron, and 90m19s for Coder. These came from the saved Phase 4
logs and included pipeline, first 50 HumanEval, and reasoning limit 10. The
same suites can compare end-to-end evaluation time on the new serving modes.

The old short-prompt runtime checks measured 137.62, 24.14, and 37.64 decode
tok/s for the older 35B quant, Nemotron, and Coder respectively. New placement probes measured
43.86 tok/s for a 50K Nemotron GPU0 chat and 44.13–47.64 tok/s for Coder at
50K–100K. The 35B five-worker layout measured about 40 tok/s per chat with
five concurrent 16K chats; its single-chat speed is lower than the old GPU0
baseline, while it offers five isolated chat slots. The old and new token
windows, occupied contexts, runtimes, and chat counts differ. A suite wall
time cannot be projected by simply dividing one tok/s figure by another:
prefill, output length, scorer work, and code execution contribute separately.

Saved broad quality reference: [MODEL_BENCHMARK_REFERENCE.md](../../MODEL_BENCHMARK_REFERENCE.md).
The current smoke is a placement and basic-quality check, not a replacement
for those full scores.
