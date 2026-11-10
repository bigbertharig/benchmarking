# Qwen3.8 Q4 64K: RAM KV and native 1060 expert peer

One Qwen3.8 Flash-Next UD-Q4_K_XL load, one 64K chat slot, INT8 KV, 8 GiB pinned expert RAM, automatic prefill, drafting off, CUDA12 engine 0.1.56, and the same additive 16K/32K/50K requests were used in all four cases. The [baseline and RAM-KV stages](../q38-q4-64k-peer-ramkv-20261110/terminal.json) ran first. The [native peer retry](terminal.json) then ran two peer cases. The first peer attempt failed because the launcher exposed only GPU0; its [diagnostic receipt](../q38-q4-64k-peer-ramkv-20261110/terminal.json) is retained and is **not a hardware fit failure**.

| Layout | 3090 expert cache | 1060 expert cache | KV backing | Complete request seconds at 16K / 32K / 50K | Prefill tok/s | Generated tok/s |
| --- | ---: | ---: | --- | --- | --- | --- |
| GPU0 baseline | 16.48 GiB / 5,650 slots | none | GPU0 VRAM | 359.8 / 318.1 / 308.1 | 55.0 / 58.9 / 67.1 | 4.9 / 7.9 / 11.9 |
| GPU0 RAM KV | 17.01 GiB / 5,831 slots | none | 20,480 cells GPU0; full K/V 0.77 GiB pinned RAM | 353.9 / 308.2 / 307.4 | 55.1 / 60.4 / 68.0 | 5.4 / 8.7 / 10.4 |
| GPU0 + native peer | 16.48 GiB / 5,650 slots | 5.21 GiB / 1,778 experts | GPU0 VRAM | 369.3 / 301.0 / 315.5 | 58.7 / 62.4 / 68.9 | 3.1 / 8.2 / 7.1 |
| Peer + RAM KV | 17.01 GiB / 5,832 slots | 5.21 GiB / 1,778 experts | 20,480 cells GPU0; full K/V 0.77 GiB pinned RAM | 363.2 / 323.5 / 314.4 | 58.5 / 59.8 / 68.8 | 3.4 / 6.1 / 7.4 |

Physical NVMe read deltas per 16K/32K/50K request were **150.6/134.9/131.3 GB** (baseline), **148.0/130.9/130.6 GB** (RAM KV), **149.3/127.7/130.3 GB** (peer), and **147.4/136.8/130.6 GB** (combined). The n-gram table and uncached experts stayed on `/data` NVMe (`/dev/nvme0n1p1`); SATA reads were under 0.1 GB per request. These host-wide counters include OS page-cache effects and should not be read as exact bytes transferred for each expert.

The native `--peer-device 1` mode **does not split model layers**. The installed engine reported 1,778 expert blobs resident on GPU1; `nvidia-smi` showed about 5,555 MiB used there. GPU0 held the model stages and the one chat in every case. This corrects the earlier `--gpu-roles` inference: roles made layer stages, whereas the native peer option really is an expert-only second-GPU tier. It does **not** put the chat on GPU1.

The peer added capacity but gave no reliable speed gain here. It improved reported prefill a little in one series, while 50K decode fell from 11.9 to 7.1 tok/s; complete-request time remained near five minutes. RAM KV added about 0.53 GiB of 3090 expert cache and had nearly unchanged complete-request time. Its log reported 98.3 to 98.4% VRAM hits for KV block reads after the first request, with hundreds of MiB fetched from RAM. Each depth is one request, so the decode variation is not a statistically stable ranking.

All completions stopped after 256 generated tokens spent in `reasoning_content`; no visible `content` or ORCHID final answer was produced. These are timing and placement receipts, not a correctness result. The full response JSON, tier traces, stage logs, and physical memory snapshots are beside this README.

The Manager job did not leave the final Strata service alive after exit despite the requested freeze. [Final loaded state](final_loaded.json) records the direct restore: 64K Q4, CUDA12, GPU0 main, GPU1 native expert peer, `--kv-resident 20480`, GPU0 23,471 MiB and GPU1 5,555 MiB. Health passed. The existing six-card benchmark claim remains active.

## What to try next

1. Preserve the current load and run a short visible-answer check with enough output budget or a supported no-thinking setting.
2. Repeat matched requests with multiple prompt contents to see whether peer cache lowers physical expert-file reads when routing changes. Measure peer hits, x1 traffic, and decode stalls.
3. Try a peer-cache ranking or placement adjustment only after the trace identifies whether peer transfers or storage misses dominate. Do not infer a speed win from capacity alone.
4. A chat resident entirely on GPU1, with model work on GPU0, is **not implemented by this Strata peer mode**. It needs a separate Qwen3.8 chat-state/attention offload path and a matched speed test.
