# Context capacity matrix campaign — 2026-10-26

The gateway docs define a planning floor, a measured compact baseline, and a GGUF trained ceiling as separate things. This campaign measures the compact baseline and the trained ceiling.

## Selection and acceptance

- Worker pool: GTX 1060 cards only (models currently tier 1–2). Brain pool: RTX 3090 Ti (tier 3). The tier-to-pool assignment is a provisional campaign rule; the manager does not yet enforce it.
- Compact case: smallest card count in the preferred homogeneous pool that fits the planning floor, then the largest projected context on that group. Try the other pure pool and then a mixed group only if needed.
- Ceiling case: first homogeneous group projected to hold the GGUF trained context, then the smallest mixed group. If none reaches it, test the best projected frontier and mark the ceiling unreachable.
- Each case uses the default benchmark profile, exact planned context, managed load/unload, a short decode probe, and 10%/90% recall probes. Pass requires a ready load, both probes, and both recall checks.
- The runner checks GPU identity and the 350W/100W power caps before every case. It is sequential, checkpointed, and writes a receipt and log per case plus a terminal receipt.
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

Manifest: campaigns/context_capacity_matrix_20261026.json. Runner: scripts/integration/run_context_capacity_matrix.py. Results: results/context_capacity_matrix_20261026/ with checkpoint.json, receipts, logs, SUMMARY.md, and terminal.json. Run through persistent rigctl run-start.

Examples of projections needing validation: Ministral 3B reaches 57,600 on one 1060 but needs the 3090 for 262,144; Ministral 14B reaches 34,304 on two 1060s and needs a mixed group for 262,144; Qwen Coder Next 80B has a six-card frontier below its trained ceiling.

