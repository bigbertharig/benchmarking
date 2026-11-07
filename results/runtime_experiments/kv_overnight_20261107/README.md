# GPU weights, worker chats, and RAM KV: overnight campaign (2026-11-07)

This campaign tests three independent hypotheses on the six-card rig:

1. Five different conversations can retain different planted facts after
   GPU0 prefill, state transfer to GPUs1–5, and concurrent continuation at
   10%, 50%, and 90% of a 256K Qwen3.6 27B context.
2. Nemotron 3.5 Bolt 74B weights can occupy GPUs0–3 while GPUs4–5 hold
   two 8K chats and then an additional 131K chat split across the same
   two worker cards. The three chats share one model object.
3. Llama 3.3 70B Q4 weights can occupy all six GPUs while its Q4 K/V cache
   resides in host RAM. A 128K configured context tests capacity; a separate
   8K 10%/90% run tests occupied-cache behavior. Qwen3 1.7B supplies a
   smaller RAM-KV depth control.

The sequence is serialized inside one Manager job with all six cards
reserved. Each case writes `.start`, `.finish`, `.exit`, `.log`, `.gpu.csv`,
`.pcie.txt`, and `.validation.json` receipts under
`results/runtime_experiments/kv_overnight_20261107/`. The raw working logs
and cache checkpoints are in `/mnt/shared/experiments/kv-matrix-20261107/`.
The campaign terminal receipt and event log are under
`/mnt/shared/experiments/kv-overnight-20261107/`.

Qwen27 recall uses five unique four-digit codes and asks each worker to
retrieve its own code. The validator records code evidence anywhere in the
generation, whether a final answer became visible, and whether that final
answer contained the correct code. These are separate measures. Synthetic
filler gives controlled depth but does not represent ordinary conversation
quality. The first 32K gate recovered all 15 codes somewhere in the
generation; its short output cap did not establish final-answer accuracy. An
8K gate with a 192-token cap also found all 15 codes but yielded only 2/15
visible correct final answers because the model spent tokens in its reasoning
section. The revised direct-answer prompt passed a separate 4K gate: 15/15
correct final answers with five concurrent chats at each of the three depths.
The 256K case requires the same 15/15 standard for a pass.

The Nemotron gate uses the exact b11669 llama.cpp revision that the Manager
runtime already uses, with a private port of the per-context cache placement
patch. The earlier private fork rejected a Nemotron tensor shape during model
loading; that is a software-version failure, not a measured capacity limit.
The new build passed a 32K gate: two 8K chats ran concurrently on GPUs4 and
5, then a third 32K chat split across those cards ran concurrently with both
small chats. Aggregate rates were 25.4 and 32.9 tokens/s for the respective
16-token phases. These short phases check placement, not steady throughput.
The four-card model split is the previously measured `56,16,9,8`. The big
chat shares GPUs4–5 with the small chats only if the two-chat phase passes.

The RAM-KV control already passed with Qwen3 1.7B weights on GPU0, a reported
1,008 MiB CPU KV buffer, and correct first-token output. Llama 70B Q4
also passed a 4K GPU-weights/CPU-KV smoke test on all six cards: the CPU KV
buffer was 360 MiB and the 32-token decode rate was 3.74 tokens/s. The run
script was replaced during that test, so its finish and exit files were
reconstructed from the Manager success record; its wall and load times are
invalid. See `llama70_smoke_provenance.txt` in the raw experiment directory.
Its GGUF is currently on shared storage, so load time includes network reads
and is not a clean speed comparison. The b11669 private port separately
passed a Qwen3 1.7B RAM-KV gate before its Nemotron gate.

The campaign checks at least 4 GiB `MemAvailable` before each case and
applies per-case timeouts. A failed case is preserved and later independent
cases continue. Completed cases are validated and reused after Manager
auto-resume. The recall case writes atomic per-chat/depth state files and can
resume its prefill from the deepest valid checkpoint. A Pi user service
waits for the campaign's terminal marker, then reloads the normal `chat-27b`
route on GPU0 and records that outcome. A model load or answer failure must
be read from its receipt; this experimental code is not a Manager profile.

## Completed results

The campaign finished at 2026-11-07T12:28:31Z with suite exit 0. All five
cases exited 0 and passed their validators. The Pi watcher completed with
exit 0 and restored the normal `chat-27b` route on GPU0.

| Case | Result |
| --- | --- |
| Qwen3.6 27B, five distinct 256K chats | All five reached 235,929 occupied tokens (90%) in separate 4,608 MiB GPU KV buffers on GPUs1-5. Concurrent recall at 10%, 50%, and 90% gave 15/15 correct final answers. The case took about 65 minutes including model load, prefill, snapshots, state transfer, and inference. |
| Nemotron 3.5 Bolt 74B, three chats | Weights loaded on GPUs0-3. Two 8K contexts on GPUs4/5 ran concurrently; adding a 131,072-capacity context split across GPUs4+5 also ran concurrently. The 64-token phases measured 27.16 and 33.23 aggregate tokens/s, respectively. The 131K context had only a short prompt, so occupied-depth capacity is not proven. |
| Qwen3 1.7B, GPU weights and RAM KV | At 32K capacity, synthetic 10% and 90% histories decoded at 51.07 and 8.19 tokens/s for 32-token samples. |
| Llama 3.3 70B Q4, GPU weights and RAM KV | All six GPUs held model layers while a 131,072-capacity Q4 K/V buffer occupied 11,520 MiB of CPU RAM. A short 32-token decode ran at 3.75 tokens/s. This establishes allocation and decode at that configured capacity, not a 128K occupied-history answer test. |
| Llama 3.3 70B Q4, RAM KV depth | With 8K capacity and synthetic histories, 32-token decode measured 2.82 tokens/s at 10% (851 used tokens) and 0.85 tokens/s at 90% (7,404 used tokens). |

The recall filler and RAM-depth histories are synthetic. Short Nemotron phases
and the 70B capacity probe should not be treated as steady-state speed or
long-context quality measurements. The 70B raw prompt also did not use the
model's instruct chat template. These configurations remain experimental
until the Manager handoff schema can express weight placement, per-context
cache placement, RAM KV, and evidence-backed occupied-depth limits.
