# Split-load reference (archived 2026-10-24)

Moved from BENCHMARK_LESSONS_LEARNED.md. Current findings: [RIG_PERFORMANCE.md](../../RIG_PERFORMANCE.md); numbers: [results/RUNTIME_REFERENCE.md](../../results/RUNTIME_REFERENCE.md). The docker commands below predate the rig manager: loads now go through `rigctl load-model`.

## Split-Load Reference

Consolidated reference for running models across multiple GPUs via tensor splitting. All findings from individual experiments above are gathered here.

### Hardware layout

| Config | Host GPUs | Docker visible | Port | Status (2026-08-03) |
|--------|-----------|----------------|------|---------------------|
| brain_extended | GPU 0 + GPU 4 | CUDA0, CUDA1 | 11434 | **Working** — 3090+1060, up to 128k ctx |
| brain_max | GPU 0 + GPU 4 + GPU 5 | CUDA0, CUDA1, CUDA2 | 11434 | **Working** — 3090+2×1060, up to 262k ctx |
| pair_1_3 | GPU 1 + GPU 3 | CUDA0, CUDA1 | 11435 | **Down** — GPUs 1-3 in "Unknown Error" state |
| pair_4_5 | GPU 4 + GPU 5 | CUDA0, CUDA1 | 11438 | **Working** — requires UUID passthrough |

### Working docker run commands

```bash
# Brain + 1 1060 (65k ctx, comfortable headroom):
docker run --rm --detach \
  --name llama-brain-split \
  --runtime=nvidia \
  -e NVIDIA_VISIBLE_DEVICES=GPU-409c0fe8-38ef-14ad-dbc6-a0437261e9cb,GPU-fd82a1a6-06aa-3ec2-1786-ae7b4474105c \
  --oom-score-adj 500 --memory 20g --memory-swap 24g \
  --network host \
  -v /mnt/shared/models/qwen3.6-27b:/mnt/shared/models/qwen3.6-27b:ro \
  llama-runtime:b8884-candidate \
  llama-server \
  --model /mnt/shared/models/qwen3.6-27b/Qwen3.6-27B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 11434 \
  --ctx-size 65536 --n-gpu-layers 999 \
  --batch-size 64 --threads 8 --parallel 1 \
  --flash-attn on -ctk q8_0 -ctv q8_0 \
  --tensor-split 4,1 --reasoning-budget 0 -fit off

# Brain + 2 1060s (262k max ctx):
docker run --rm --detach \
  --name llama-brain-split \
  --runtime=nvidia \
  -e NVIDIA_VISIBLE_DEVICES=GPU-409c0fe8-38ef-14ad-dbc6-a0437261e9cb,GPU-fd82a1a6-06aa-3ec2-1786-ae7b4474105c,GPU-d24dca6a-b19f-2018-57b7-15a79466efdf \
  --oom-score-adj 500 --memory 20g --memory-swap 24g \
  --network host \
  -v /mnt/shared/models/qwen3.6-27b:/mnt/shared/models/qwen3.6-27b:ro \
  llama-runtime:b8884-candidate \
  llama-server \
  --model /mnt/shared/models/qwen3.6-27b/Qwen3.6-27B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 11434 \
  --ctx-size 262144 --n-gpu-layers 999 \
  --batch-size 64 --threads 8 --parallel 1 \
  --flash-attn on -ctk q8_0 -ctv q8_0 \
  --tensor-split 4,1,1 --reasoning-budget 0 -fit off

# Worker split (1060 pair, standard via run_runtime.sh when GPUs healthy):
bash /mnt/shared/scripts/llama_runtime/run_runtime.sh \
  --name llama-split-pair45 \
  --model /mnt/shared/models/<model-dir>/<model>.gguf \
  --port 11438 \
  --gpus "device=4,5" \
  --tensor-split 1,1 \
  --ctx-size 16384 \
  --memory-limit 10g --memory-swap 12g \
  --extra-arg "-fit" --extra-arg "off"
```

### GPU UUIDs (for when `--gpus device=N,M` fails)

```
GPU 0: GPU-409c0fe8-38ef-14ad-dbc6-a0437261e9cb  (3090 Ti)
GPU 4: GPU-fd82a1a6-06aa-3ec2-1786-ae7b4474105c  (1060 6GB)
GPU 5: GPU-d24dca6a-b19f-2018-57b7-15a79466efdf  (1060 6GB)
```

Obtain fresh UUIDs with: `nvidia-smi -L 2>/dev/null | grep UUID`

### Tested split configurations

**Brain model (Qwen3.6-27B) across mixed architectures:**

| ctx_size | GPUs | tensor-split | GPU 0 (3090) | GPU 4 (1060) | GPU 5 (1060) | KV cache | Status |
|----------|------|-------------|-------------|-------------|-------------|----------|--------|
| 8,192 | 1 (baseline) | — | 16,273 MiB | — | — | ~442 MiB | Working |
| 32,768 | 2 | 4,1 | 12,953 MiB | 4,214 MiB | — | 1,088 MiB | Working |
| 65,536 | 2 | 4,1 | 13,873 MiB | 4,434 MiB | — | 2,176 MiB | Working (recommended) |
| 131,072 | 2 | 4,1 | — | — (tight) | — | 4,352 MiB | Working (1060 near limit) |
| 131,072 | 3 | 4,1,1 | 13,413 MiB | 3,154 MiB | 4,196 MiB | 4,352 MiB | Working |
| 262,144 | 3 | 4,1,1 | 16,549 MiB | 3,762 MiB | 5,076 MiB | 8,704 MiB | Working (max) |

**Worker models across 1060 pairs:**

| Model | CUDA0 MiB | CUDA1 MiB | CPU MiB | Layers | ctx_size | Status |
|-------|-----------|-----------|---------|--------|----------|--------|
| Gemma-4-12B Q4_K_M | 3,102 | 3,786 | 924 | 48/48 | 4,096 | Working (pair_1_3) |
| Qwen2.5-Coder-14B Q4_K_M | 3,917 | 4,231 | 418 | 49/49 | 16,384 | Working (pair_4_5) |
| Phi-4-14B Q4_K_M | — | — | — | 41/41 auto | 16,384 | Working (no forced layers) |

**Brain MoE across the 1060 farm, no 3090 (2026-10-17):**

Model `nex-n2.5:mini` (35B MoE, 3B active, 22.3 GB GGUF), `llama-runtime:b11669`, layer split, ctx 8192,
768-token decode, from the NVMe hot-set. The 3090 was serving qwen3.6:35b-a3b (its Phase 4 tests) during
both runs; the rig stayed up.

| GPUs | tensor-split | Model buffers per card (MiB) | VRAM used per card | Load | Decode tok/s | Prompt tok/s (63-token prompt) | Avg W per card | Status |
|------|--------------|-------------------------------|--------------------|------|--------------|-------------------------------|----------------|--------|
| 1 (3090 alone) | — | 20,758 total | 21,275 of 24,564 | 253 s (NFS) | 142.2 | 508 | 295 | reference |
| 5 (GPUs 1-5) | 1,1,1,1,1 | 5,153 / 3,827 / 3,761 / 3,827 / 4,192 | 3,914-5,318 | 212 s | 21.7 | 69 | 30-41 | Working |
| 4 (GPUs 1-4) | 1,1,1,1 | — | — | — | — | — | — | Fails: does not fit |
| 4 (GPUs 1-4) | 0.75,1,1,1 | 5,153 / 5,235 / 5,176 / 5,195 | 5,318-5,400 of 6,144 | 212 s | 22.0 | 79 | 33-52 | Working (~750 MB free per card) |
| 5 (GPUs 1-5) | 1,1,1,1,1 + `--split-mode row` | — | — | — | — | — | — | Fails: "device CUDA0 does not support split buffers" |

Working command (4-way, through `run_runtime.sh`, which holds the rig-wide load lock):

```bash
~/llm_orchestration/shared/scripts/llama_runtime/run_runtime.sh \
  --name llama-nex-split4 \
  --model /data/model-hotset/nex-n2.5-mini/nex-agi_Nex-N2.5-mini-Q4_K_M.gguf \
  --port 11445 --gpus device=1,2,3,4 --ctx-size 8192 --batch-size 128 \
  --tensor-split 0.75,1,1,1 --memory-limit 10g --memory-swap 12g \
  --extra-arg --chat-template-kwargs --extra-arg '{"reasoning_effort":"none"}' \
  --extra-arg -fit --extra-arg off
```

Findings:
- **Speed:** about 6.5x slower than the 3090 for this MoE, the same pattern as the April gemma-4:26b-a4b
  split (6.3x); 4-way and 5-way decode at the same speed. See
  `llm_orchestration/shared/workspace/distributed_work_guide.md` for the full speed table.
- **Load is light per card:** a layer split runs the cards one after another per token, so each 1060 sat
  at 14-33% utilization and 30-52 W average (72 W peak) while decoding.
- **First card carries a fixed extra:** CUDA0 held 5,153 MiB in both the 4- and 5-way loads, about 1.3 GB
  above its layer share, so equal weights overfill it on 4 cards. Lower its weight (0.75 worked).
- **Quality:** litmus 3/3 on both. Greedy outputs diverge from the 3090 (2 of 10 GSM8K responses
  identical) because Pascal and Ampere kernels differ; the 4- and 5-way splits agree with each other.
  GSM8K limit 10 scored 0.80 on both splits vs 0.90 on the 3090: two split answers took a more verbose
  path and were cut by the GSM8K default output budget, and one question flipped the other way.
- **Row split** is not available for this hybrid recurrent architecture in b11669, so tensor parallelism
  across the 1060s cannot be tested with the October brain candidates.
- **Concurrency:** both runs ran while the 3090 served another model (3090 at about 270-334 W); no reset.

Records: `results/runtime_experiments/nex_n25_mini_split5_concurrent_runtime_characterization_20261017.json`,
`results/runtime_experiments/nex_n25_mini_split4_runtime_characterization_20261017.json`; ledger GSM8K rows
under suites `nex_n25_mini_split5_concurrent` and `nex_n25_mini_split4`.

### PCIe generation and split scaling (2026-10-19)

qwen2.5-coder:7b (Q4_K_M), ctx 8192, through the harness (`rigctl load-model --gpus`), `llama-runtime:b11669`.
Decode: median of 3 x 256 tokens. Prefill: median of 3 unique 3761-token prompts. GPU 3 links at Gen1 in
both runs and joins last. Tool: llm-gateway `tools/split_sweep.py`.

| GPUs | Hops | Decode tok/s Gen2 | Decode tok/s Gen3 | Prefill tok/s Gen2 | Prefill tok/s Gen3 |
|------|------|------|------|------|------|
| 1 | 0 | 22.3 | 22.9 | 319 | 323 |
| 1,2 | 1 | 23.6 | 24.4 | 364 | 374 |
| 1,3 (Gen1 hop) | 1 | 22.0 | 22.2 | 349 | 357 |
| 1,2,4 | 2 | 22.1 | 23.3 | 383 | 398 |
| 1,2,4,5 | 3 | 22.8 | 23.2 | 377 | 396 |
| 1,2,4,5,3 | 4 | 22.3 | 22.8 | 369 | 387 |
| 5-card, `-b 2048 -ub 128` | 4 | 23.1 | 23.8 | 487 | 502 |
| 5-card, `-b 2048 -ub 512` | 4 | 22.7 | 22.0 | 889 | 903 |
| 5-card, `-b 2048 -ub 2048` | 4 | 21.6 | 23.4 | 507 | 520 |

qwen3.6:35b-a3b on GPUs 1-5 (8,8,8,8,9 layers, ctx 89344), cold page cache, then 10 minutes of
long unique prompts (about 5-8k tokens) plus decode requests, 3 at a time (`tools/pcie_split_test.py`):

| | Gen2 | Gen3 |
|---|---|---|
| Cold load (NVMe hot-set) | 132 s | 90 s |
| Prefill / decode | 355 / 24.5 tok/s | 364 / 25.9 tok/s |
| Requests, errors | 28, 0 | 29, 0 |
| Link replays after (GPU 1/2/4/5) | 0/0/0/0 | 15162/51386/65535/12370 |

Findings:
- **Decode does not depend on hops or PCIe speed.** 0 to 4 hops stay within card-to-card variation, and the
  single card (no hops) moved by as much as the splits between Gen2 and Gen3. A layer split runs the cards
  one after another; each 1060's VRAM bandwidth sets the speed. A split buys capacity, not decode speed.
- **The links are nearly idle during split inference:** 6-58 MB/s per 1060 in each direction against about
  500 MB/s for Gen2 x1. Cards sat at 17-32% utilization and 26-36 W.
- **Micro-batch is the big prefill lever.** The 1060 profiles use batch 64; `-b 2048 -ub 512` gave 2.4x the
  prefill (369 to 889 tok/s) on the 5-card split with no decode cost. 2048 fell back to about 510.
- **Gen3 helps loads only.** NVMe O_DIRECT read 434 to 847 MB/s; cold mmap read (what llama.cpp does)
  438 to 503 MB/s; cold 5-way load 132 to 90 s. The GPU links at Gen3 logged replays on every 1060 riser
  link, so the BIOS stays at Gen2 (llm_orchestration `systems_prep.md` item 8).
- **Gen1 vs Gen2 hop:** GPUs 1+3 ran about 3 ms/token slower than 1+2, but GPU 3 is both the Gen1 link and a
  different board; not separated yet.

Records: `results/runtime_experiments/split_scaling_pcie_gen2_20261019.json`,
`results/runtime_experiments/split_scaling_pcie_gen3_20261019.json`.

### Known failures and restrictions

| Model | Issue | Bug/Workaround |
|-------|-------|----------------|
| Qwen3.6-27B | Tensor split bug #22058 | **Actually works** on 3090+1060 with b8884-candidate. Bug may be version/config specific. |
| Gemma-3-12B | 262K vocab embedding too large | ~3.1GB embedding per GPU exceeds 6GB VRAM |
| Phi-4-14B | `--n-gpu-layers 999` aborts | Remove forced layer count, let auto-fitter work |
| Any model | `--gpus device=N,M` with errored GPUs | Use UUID passthrough via `--runtime=nvidia` + `-e NVIDIA_VISIBLE_DEVICES` |
| nex-n2.5:mini (qwen35moe hybrid recurrent) | `--split-mode row` fails: "device CUDA0 does not support split buffers" (b11669) | Use layer split (default) |
| nex-n2.5:mini on 4x 1060 | Equal tensor-split overfills CUDA0 (fixed ~1.3 GB extra on the first card) | `--tensor-split 0.75,1,1,1` |

### Critical rules

1. **tensor-split values = visible GPU count** — `--tensor-split 4,1` for 2 GPUs, `4,1,1` for 3. NOT physical index masks.
2. **`-fit off` required** when using `--n-gpu-layers 999` — prevents auto-fitter from aborting
3. **Gemma 4 / Qwen 3.6 need `llama-runtime:b8884-candidate`** — default image doesn't support these architectures
4. **Docker memory limits**: 20g/24g for brain split (KV cache at high ctx dominates); 10g/12g for worker splits
5. **mmap ON** (default) — do NOT add `--no-mmap` (causes Docker OOM, see `--no-mmap` section above)
6. **Port convention**: brain → 11434, pair_1_3 → 11435, pair_4_5 → 11438
7. **Weight the tensor-split toward the 3090** — `4,1` or `4,1,1` keeps most weights on the faster GPU
8. **On the 1060 farm, weight the first card down** — CUDA0 carries a fixed extra (~1.3 GB for Nex), so
   give it a smaller share (`0.75,1,1,1`) when the split is near capacity
9. **4-way and 5-way 1060 splits decode at the same speed** — use the fewest cards that fit and keep the
   rest free for other work
