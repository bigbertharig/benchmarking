# Context capacity matrix campaign — 2026-10-26

The gateway docs define a planning floor, a measured compact baseline, and a GGUF trained ceiling as separate things. This campaign measures the compact baseline and the trained ceiling.

## Selection and acceptance

- Worker pool: GTX 1060 cards only (models currently tier 1–2). Brain pool: RTX 3090 Ti (tier 3). The tier-to-pool assignment is a provisional campaign rule; the manager does not yet enforce it.
- Compact case: smallest card count in the preferred homogeneous pool that fits the planning floor, then the largest projected context on that group. Try the other pure pool and then a mixed group only if needed.
- Ceiling case: first homogeneous group projected to hold the GGUF trained context, then the smallest mixed group. If none reaches it, test the best projected frontier and mark the ceiling unreachable.
- Stage 1a is maximum sizing only: for each compact or ceiling/frontier card set, ask the manager for its configured minimum and maximum context, then load at the suggested maximum and unload. The configured minimum is a planning floor; compact means the largest validated context on the smallest selected preferred-pool group.
- Stage 1b separately loads each of the 28 models at its manager-suggested minimum context on its compact GPU group, then unloads. A sizing pass requires the requested GPUs and context, a ready load, measured full GPU offload, and a clean unload.
- Stage 2 uses only the validated Stage 1a contexts. It runs the short decode probe and uncached 10%/90% depth/recall probes. The first scheduled depth job defers to Stage 1b; a second depth job starts automatically only after both sizing passes succeed. Any sizing failure holds depth for correction. None of these stages automatically promotes the model library.
- Both runners check GPU identity and the 350W/100W power caps before every case. They are sequential and checkpointed with per-case receipts; the depth runner also writes per-case logs. Sequential loads keep VRAM allocation and load timing attributable to one case.
- Paired fast/slow tests follow at the same GGUF, context, batch, runtime, and prompt. A 1060-only fallback is available only when that same context fits. Automatic pool ordering remains future manager work.

## Planned cases (projections, not results)

| Model | Preferred pool | Compact GPUs / ctx | Ceiling or frontier GPUs / ctx | Trained ceiling projected reachable? |
|---|---|---|---|:---:|
| devstral-small:24b | brain | 0 / 117,504 | 0,1,2,3,4,5 / 259,072 | no |
| gemma-4:12b | worker | 1,2 / 207,616 | 1,2,3 / 262,144 | yes |
| gemma-4:26b-a4b | brain | 0 / 262,144 | 0 / 262,144 | yes |
| gemma-4:31b | brain | 0 / 93,440 | 0,1,2,3,4 / 262,144 | yes |
| gemma-4:e2b-q8 | worker | 1 / 131,072 | 1 / 131,072 | yes |
| gemma-4:e4b | worker | 1 / 131,072 | 1 / 131,072 | yes |
| gpt-oss:20b | brain | 0 / 131,072 | 0 / 131,072 | yes |
| llama3.2:3b | worker | 1 / 53,760 | 1,2,3 / 131,072 | yes |
| mellum2.1:12b-a2.5b | worker | 1,2 / 129,280 | 1,2,3 / 131,072 | yes |
| minicpm5:2b | worker | 1 / 131,072 | 1 / 131,072 | yes |
| ministral-3:14b | worker | 1,2 / 34,304 | 0,1,2,3 / 262,144 | yes |
| ministral-3:3b | worker | 1 / 57,600 | 0 / 262,144 | yes |
| ministral-3:8b | worker | 1 / 9,216 | 0,1 / 262,144 | yes |
| nex-n2.5:mini | brain | 0 / 141,568 | 0,1 / 262,144 | yes |
| ornith-1.5:35b-a3b | brain | 0 / 188,672 | 0,1 / 262,144 | yes |
| ornith-1.5:9b | worker | 1 / 25,344 | 1,2,3 / 262,144 | yes |
| phi-4-mini-reasoning:3.8b | worker | 1 / 41,216 | 1,2,3 / 131,072 | yes |
| phi-4:14b | worker | 1,2 / 16,384 | 1,2 / 16,384 | yes |
| qwen2.5-coder:14b | worker | 1,2 / 20,224 | 1,2,3 / 32,768 | yes |
| qwen2.5-coder:7b | worker | 1 / 32,768 | 1 / 32,768 | yes |
| qwen3-coder:30b-a3b | brain | 0 / 112,128 | 0,1,2,3,4 / 262,144 | yes |
| qwen3.5:27b | brain | 0 / 209,664 | 0,1,2 / 262,144 | yes |
| qwen3.6:27b | brain | 0 / 208,384 | 0,1,2 / 262,144 | yes |
| qwen3.6:35b-a3b | brain | 0 / 243,968 | 0,1 / 262,144 | yes |
| qwen3.8:27b | brain | 0 / 190,720 | 0,1,2 / 262,144 | yes |
| smollm3:3b | worker | 1 / 65,536 | 1 / 65,536 | yes |
| qwen3-coder-next:80b-a3b | brain | 0,1,2,3,4,5 / 185,600 | 0,1,2,3,4,5 / 185,600 | no |
| nemotron-3.5-bolt:74b-a9b | brain | 0,1,2,3 / 35,584 | 0,1,2,3,4,5 / 262,144 | yes |

Plan: 28 models and 47 distinct cases. A compact case that already reaches the ceiling runs once. Planned GPU indices are checked before each case.

Manifest: campaigns/context_capacity_matrix_20261026.json. Sizing runner: scripts/integration/run_context_capacity_sizing.py; receipts and terminal status: results/context_capacity_sizing_20261026/. Once all maximum cases pass, it writes validated_manifest.json and schedules scripts/integration/run_context_capacity_matrix.py. That job defers to scripts/integration/run_context_capacity_min_sizing.py, whose 28 load/unload receipts and terminal status live in results/context_capacity_min_sizing_20261026/. After all minimum cases pass, it restarts the depth job with results/context_capacity_validated_depth_20261026/. All stages use persistent rigctl runs.

The original combined depth run started at 2026-10-26 14:51 PDT and was stopped at 15:22 PDT after six compact cases passed; those receipts remain under results/context_capacity_matrix_20261026/. Its interrupted Nemotron load was explicitly unloaded. The new sizing-only job started at 15:26 PDT and reused a separately verified Ministral 8B startup case. The stopped run will not auto-resume. The manager's GGUF path is the NFS catalog address; the rig runtime selected /data/model-hotset for the observed staged models. Load times must retain their actual source-path context when compared.

Examples of projections needing validation: Ministral 3B reaches 57,600 on one 1060 but needs the 3090 for 262,144; Ministral 14B reaches 34,304 on two 1060s and needs a mixed group for 262,144; Qwen Coder Next 80B has a six-card frontier below its trained ceiling.

## 2026-10-27 compact retry and Phi output follow-up

The validated-depth campaign completed with 42/47 cases passing. Four compact cases hit the manager's fit limit and Phi-4 Mini Reasoning reached 90% depth but spent its 160 generated tokens inside raw `<think>` text. Qwen3-Coder-Next remains a separate six-card placement issue and is deferred by operator request.

The targeted retry `campaigns/context_capacity_small_retry_20261027.json` ran from 13:11 to 13:27 PDT. All three revised compact placements loaded and passed both 10% and 90% recall:

| Model | GPUs | Observed ctx | Load | Result |
|---|---|---:|---:|---|
| Ornith 1.5 9B | 1 | 24,064 | 38.6 s | pass |
| Ministral 3 3B | 1 | 56,832 | 25.1 s | pass |
| Devstral Small 24B | 0 | 115,200 | 48.2 s | pass |

Receipts, logs, checkpoint, and terminal status: `results/context_capacity_small_retry_20261027/`. These results validate the reduced compact contexts; they do not automatically promote profile defaults.

Phi-4 Mini Reasoning at 131,072 loaded context on GPUs 1,2,3 recalled the planted code at 10% depth with 512, 1,024, and 2,048 generated-token limits. All three forced-decode runs exhausted the limit inside raw `<think>` text, so their `recall_ok` does not establish a usable final answer. A 2,048-token normal-EOS run without prompt changes did the same. The 2,048-token receipts record `final_recall_ok=false` and `raw_think_closed=false`.

Two 10% runs with normal EOS and a concise system instruction produced final answers containing the planted code. The first stopped after 857 tokens and returned only the code; the second stopped after 250 tokens and included the code with extra formatting. Both have `final_recall_ok=true`, `raw_think_closed=true`, and `finish_reason=stop`. This prompt variant is distinct from the earlier capacity methodology. Receipts are under `results/runtime_experiments/phi-mini-10pct-*-20261027.json`.

The 90% follow-up with the same settings (`phi-mini-90pct-2048-concise-20261027`) ran from 13:46 to 14:19 PDT and did not pass. At 117,678 prompt tokens, time to first token was 1,566.5 s, prefill was 75.12 tok/s, and decode was 5.31 tok/s. It exhausted all 2,048 generated tokens in an unclosed raw `<think>` response, with no final answer and no planted-code recall (`recall_ok=false`, `final_recall_ok=false`). Its load took 18.4 s at 131,072 allocated context. This establishes a usable 10% prompt variant but no usable 90% result. Do not promote deep-context Phi behavior or infer that a larger answer budget would fix recall. Defer another deep probe until a distinct output/recall fix has passed shorter trials.
