# Matched whole-expert placement, Nemotron 3.5 Bolt (2026-11-07)

This experiment compares two placements of the *same* Nemotron 3.5 Bolt 74B
UD-Q3_K_XL GGUF and the same private llama.cpp b11669 build. The 3090 Ti
(CUDA0) holds all non-overridden weights. Four GTX 1060s (CUDA1-4) hold whole
routed expert tensors. Worker 4's 8K KV cache is on CUDA4, worker 5's 8K KV
cache is on CUDA5, and a third context is split across CUDA4+5. Both layouts
use `KV_MODEL_DEVICES=0,1,2,3,4` and `KV_MODEL_SPLIT=88,0,0,0,0`. Q4 K/V,
greedy sampling, prompts, and token counts stay fixed within each phase.

The GGUF is staged once on the rig's local SATA volume before the measured
sequence; `stage_model.sh` records the copy size, timing, and exit status.
The contiguous layout is the previous four-group placement: each 1060 owns a
successive span of MoE layers. The balanced interleaved layout redistributes
those layers across the same four cards. `inventory.json` is a header-only
GGUF tensor inventory. `balance_layout.py` uses its actual expert byte sizes
to choose groups with the same layer counts (7/5/5/5) and within 3.4 MiB of
the contiguous expert bytes on each card. The resulting override rules are in
`interleaved_balanced.tsv`; `contiguous.tsv` is the control.

Short-history cases run 256 timed output tokens per chat: first two 8K chats,
then both plus a third chat with 131K *configured* capacity. That large
context is not filled. Depth cases configure the third chat at 32K, fill all
three contexts to 10% and then 90% using the same synthetic text, and time 128
concurrent output tokens per chat at each depth. The sequence is contiguous,
balanced interleaved, contiguous for short-history drift control, followed by
balanced interleaved and contiguous depth cases.

`analyze_matched_placement.py` requires successful exits, one model load per
run, completed phases, and identical first-token outputs (Tokyo, Berlin,
Ottawa). Raw logs, 1 Hz GPU memory/utilization samples, PCIe rate samples,
timestamps, exit receipts, scripts, and model inventory are archived here.
The PCIe samples are not synchronized to phase boundaries and do not measure
exact transferred bytes. The timed decode rates exclude model load time.

An initial interleaved pilot on shared storage was rejected: it put 5,380 MiB of model weights
on CUDA1 versus 4,001 MiB in the control. That pilot and the aborted campaign
remain under `/mnt/shared/experiments/kv-expert-chat-20261107/` as provenance;
they are excluded from the matched comparison. A subsequent generated override
file had Windows CRLF endings and matched no expert tensor, causing a pre-decode
CUDA0 OOM. Its failed load receipt is archived and the preflight now checks
line endings and all 44 intended tensor matches. A routing trace was not used
to choose the layout. This build can move whole expert tensors, while the
hot-expert idea requires placement or caching within each tensor.

## Short-history result

All three local-source runs exited 0 and passed the first-token, one-load,
phase-completion, and model-buffer checks. The actual model allocations on
CUDA1-4 differed by less than 3.4 MiB between layouts. Peak sampled CUDA0
usage was 21,491 MiB in every run; peak CUDA4 was 4,638 MiB for contiguous
and 4,636 MiB for balanced interleaved. Both layouts reported graph split
counts of 62 and 68 across their contexts.

| Run | Two 8K chats, aggregate tok/s | Plus 131K-capacity paired chat, aggregate tok/s |
| --- | ---: | ---: |
| Contiguous A1 | 64.09 | 71.44 |
| Balanced interleaved B | 61.88 | 68.49 |
| Contiguous A2 | 61.21 | 71.23 |

The interleaved two-chat rate sits within the control's run-to-run spread.
With the third chat added, it is 3.98% below the mean of the two controls.
This short-history pass does not establish why: graph split counts and peak
GPU allocations are effectively identical. The 131K context was allocated
but not filled.

## Occupied-depth result

Both local-source depth runs exited 0, produced the same first tokens, and
reached 819/7,372 tokens on each 8K chat and 3,276/29,491 on the paired 32K
chat. All model buffers matched within 5 MiB. The paired 90% fill took 538.28
seconds with balanced interleaving and 538.20 with contiguous placement.

| Layout | 10% aggregate tok/s | 90% aggregate tok/s | Peak CUDA4 MiB |
| --- | ---: | ---: | ---: |
| Balanced interleaved | 43.55 | 14.45 | 4,402 |
| Contiguous | 44.32 | 14.54 | 4,404 |

Balanced interleaving was 1.73% slower at 10% and 0.60% slower at 90% in
this single matched pass. Together with the short A/B/A controls, this gives
no evidence that redistributing whole expert *layers* across the same four
1060s helps. The existing contiguous whole-expert placement remains the
better supported recipe. The archived PCIe rate samples cannot establish a
transferred-byte difference or explain the small speed gaps.

The routing-trace idea from BigMoeOnEdge remains a separate experiment:
these GGUF overrides move an entire layer's expert tensor, so every routed
expert in that tensor travels together. Exploiting a measured hot set requires
an expert-granularity cache or transfer path, with per-token routing and
transfer measurements. It also needs a matched comparison with the same
1060 chat layout; this run supplies that whole-tensor control.
