# Context profile audit — 2026-10-26

Read-only planner projection using the current gateway catalog, all cards idle, and the existing load observations. GPU0 is a 24,564 MiB 3090; GPUs1–5 are 6,144 MiB 1060s. The maximum column is a GGUF trained-context ceiling, not a verified quality or full-depth result. A projected fit still requires a real load to confirm memory. Card choice and micro-batch also affect the projected result.

The default mode keeps the selected profile working context; `min` uses its lower bound; `max` searches the highest context that fits on the named cards. All values below are context tokens. Profiles with a different chat or worker working context show that value in parentheses.

| Model | Status | Default working | Min | GGUF max | 1×1060 at min | 2×1060 max fit | 3090 max fit |
|---|---|---:|---:|---:|:---:|---:|---:|
| `devstral-small:24b` | active | 4.0K (chat 32.0K) | 4.0K | 384.0K | no | — | 114.0K |
| `gemma-4:12b` | active | 4.0K | 4.0K | 256.0K | no | 202.0K | 256.0K |
| `gemma-4:26b-a4b` | active | 16.0K | 8.0K | 256.0K | no | — | 256.0K |
| `gemma-4:31b` | active | 16.0K | 8.0K | 256.0K | no | — | 91.0K |
| `gemma-4:e2b-q8` | active | 4.0K | 4.0K | 128.0K | yes | 128.0K | 128.0K |
| `gemma-4:e4b` | active | 4.0K | 4.0K | 128.0K | yes | 128.0K | 128.0K |
| `gpt-oss:20b` | active | 16.0K (chat 64.0K) | 8.0K | 128.0K | no | — | 128.0K |
| `llama3.2:3b` | active | 4.0K | 4.0K | 128.0K | yes | 119.0K | 128.0K |
| `mellum2.1:12b-a2.5b` | candidate | 8.0K | 8.0K | 128.0K | no | 126.0K | 128.0K |
| `minicpm5:2b` | candidate | 4.0K | 4.0K | 128.0K | yes | 128.0K | 128.0K |
| `ministral-3:14b` | active | 8.0K | 8.0K | 256.0K | no | 33.0K | 171.0K |
| `ministral-3:3b` | active | 16.0K (worker 8.0K) | 8.0K | 256.0K | yes | 117.0K | 256.0K |
| `ministral-3:8b` | active | 16.0K (worker 8.0K) | 8.0K | 256.0K | yes | 73.0K | 243.0K |
| `nex-n2.5:mini` | candidate | 8.0K (chat 64.0K) | 8.0K | 256.0K | no | — | 138.0K |
| `ornith-1.5:35b-a3b` | candidate | 8.0K | 8.0K | 256.0K | no | — | 184.0K |
| `ornith-1.5:9b` | active | 8.0K | 8.0K | 256.0K | yes | 233.0K | 256.0K |
| `phi-4-mini-reasoning:3.8b` | active | 4.0K | 4.0K | 128.0K | yes | 103.0K | 128.0K |
| `phi-4:14b` | active | 8.0K | 8.0K | 16.0K | no | 16.0K | 16.0K |
| `qwen2.5-coder:14b` | active | 8.0K (worker 16.0K) | 8.0K | 32.0K | no | 19.0K | 32.0K |
| `qwen2.5-coder:7b` | active | 16.0K | 8.0K | 32.0K | yes | 32.0K | 32.0K |
| `qwen3-coder:30b-a3b` | active | 16.0K (chat 32.0K) | 8.0K | 256.0K | no | — | 109.0K |
| `qwen3.5:27b` | active | 16.0K | 8.0K | 256.0K | no | — | 204.0K |
| `qwen3.6:27b` | active | 16.0K (chat 64.0K) | 8.0K | 256.0K | no | — | 203.0K |
| `qwen3.6:35b-a3b` | active | 16.0K | 8.0K | 256.0K | no | — | 238.0K |
| `qwen3.8:27b` | candidate | 16.0K | 8.0K | 256.0K | no | — | 186.0K |
| `smollm3:3b` | active | 4.0K | 4.0K | 64.0K | yes | 64.0K | 64.0K |
| `qwen3-coder-next:80b-a3b` | candidate | 16.0K | 8.0K | 256.0K | no | — | — |
| `nemotron-3.5-bolt:74b-a9b` | active | 16.0K | 8.0K | 256.0K | no | — | — |

For example, `ministral-3:8b` defaults to 16K, fits one 1060 at its 8K minimum, and projects up to about 73.3K on two 1060s or 243.8K on the 3090 with its default micro-batch. These larger contexts are capacity projections, not benchmark recommendations.

Models with a 4K minimum use that because the default working profile is already 4K. Models with a larger default working context have an 8K minimum, including the Ministral 8B case. Devstral interactive also has an 8K minimum. These are policy bounds, not independently validated quality thresholds.
