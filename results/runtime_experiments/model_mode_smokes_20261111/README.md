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
The Manager job was `model_mode_smokes_20261111_v2`, with all-card claim
`model-mode-smokes-v2-20261111`. The first queue was stopped before any model
switch to correct the 35B registry ID from the older Q4_K_M entry to the active
Q4_K_XL entry. The completed series left the 35B mode loaded; the claim was
released afterward.

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

## Results and correction

The sequence terminal receipt reports `passed`: Coder, Nemotron, and the first
35B XL load completed all Phase 4 stages. Coder used its already-resident
30-layer server; Nemotron and 35B were loaded through the named orchestration
command. The initial 35B stage was **invalid as a quality check despite its
successful process exits**. Thinking filled short generation budgets and put
text in `reasoning_content`, leaving ordinary answer `content` empty. A direct
64-token arithmetic request reproduced the problem. Orchestration mode
`single-chat-fast` now passes `--reasoning off`; after reloading, the same
request returned `content: "4"`. The corrected 35B Phase 4 job is
`qwen35_mode_fix_smoke_20261112`, using run tag
`qwen35_single_chat_fast_reasoningoff_smoke_20261112`. Its pipeline passed
6/6 stages, code completed 50/50 generations, and all five reasoning tasks
completed. All 50 corrected HumanEval generations had nonempty answer text.

| Load and smoke | Suite wall time, no cold load | HumanEval base (50) | BBH flexible (270) | MMLU-Pro flexible (140) | DROP F1 (10) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Coder 30x5, resident server | 75m44s | 98% | 72.2% | 81.4% | 38.5% |
| Nemotron, GPU0 chat / four expert 1060s | 59m29s | 98% | 86.3% | 66.4% | 82.9% |
| 35B XL, thinking enabled **invalid** | 52m58s | 4% | 42.2% | 24.3% | 0% |
| 35B XL, thinking disabled | 20m03s | 98% | 90.4% | 80.7% | 80.0% |

The corrected 35B result is much faster than its invalid thinking-enabled
control on this smoke workload. Coder and Nemotron finished about 16% and 20%
faster than their older Phase 4 smoke wall times; those older runs used other
loading settings and are contextual comparisons. The older 35B wall time used
the Q4_K_M quant, so it is not a matched speed baseline for this XL run.
These limited smoke scores are not replacements for full model rankings.

Nemotron's first named load read the 39.0 GB model from the NFS archive and
timed out after 900 seconds before GPU allocation. The stopped Coder NVMe copy
was removed after checking the archive copy remained the same size. Nemotron
was copied sequentially to a hidden NVMe file, checked at the expected byte
count, and promoted to the hotset. The retried load resolved that NVMe file and
passed. No repeated whole-file hash was needed for this temporary hotset swap.
The failed stage and successful retry remain in the sequence receipts.

After the corrected smoke, the 35B XL service remains ready on GPU0 at port
11524 with a 16K context. The all-card benchmark claim and the later GPU0-only
correction claim were released when their work ended. GPU availability should
be read from the rig controller before starting a new model.

## GPU0 short-decode confirmation

The corrected 35B XL server was already running with weights and Q8 KV on CUDA0 (3090), 16K context cap, and reasoning off. Two 384-token `/completion` probes with a 37-token prompt measured **152.07 and 152.04 decode tok/s** (about 2.52 s of decode each). See [receipt](qwen35_gpu0_decode_probe_20261112.json). This confirms a 3090-resident chat can reach the same general short-context speed class as the earlier 137.62 tok/s result; the earlier result used Q4_K_M and is not an isolated placement comparison. These short probes do not describe 50K context or concurrent worker speeds.

## GPU0 main plus five 1060 chats

A 262K-cap Q4 main context on GPU0 and five 262K-cap Q4 worker contexts on GPUs1?5 ran with all Q4_K_XL model weights on GPU0. At 16K/32K/50K occupied context, the 64-token simultaneous decode windows measured main **98.39/88.60/86.02 tok/s** and workers **25.47?26.26 / 18.13?18.82 / 13.47?13.90 tok/s**. GPU0 peak was 23,567 MiB of 24,564 MiB; each 1060 peaked at 2,037 MiB of 6,144 MiB. The main solo windows in the same run were 100.62/113.25/103.14 tok/s. See [six-chat receipt](qwen35_gpu0_main_five_workers_20261112.json) and raw GPU samples/log.

Two validated checkpoint histories were cloned into separate worker contexts for GPUs3?5. This proves six concurrent KV allocations and decode streams; distinct prior contents for all five workers were not checked in this replay. The short windows do not establish long-response or full-turn latency. The runner gains `moe_main_five_replay` for repeatability. The named single-chat-fast server was reloaded after the run.
