# Context capacity matrix results

Manifest: `context-capacity-validated-20261026`. Results as of 2026-10-27T17:20:53+00:00.
These are observed loads and 10%/90% recall probes, not automatic library promotions.

| Model | Target | GPUs | Planned ctx | Observed ctx | Load s | Recall | Status |
|---|---|---|---:|---:|---:|---|---|
| `ministral-3:8b` | compact | 1 | 9216 | 9216 | 38.3 | pass | passed |
| `phi-4:14b` | compact | 1,2 | 16384 | 16384 | 54.8 | pass | passed |
| `qwen2.5-coder:14b` | compact | 1,2 | 21504 | 21504 | 117.7 | pass | passed |
| `ornith-1.5:9b` | compact | 1 | 24320 | — | — | fail | failed |
| `qwen2.5-coder:7b` | compact | 1 | 32768 | 32768 | 35.0 | pass | passed |
| `ministral-3:14b` | compact | 1,2 | 33792 | 33792 | 51.5 | pass | passed |
| `nemotron-3.5-bolt:74b-a9b` | compact | 0,1,2,3 | 96256 | 96256 | 203.1 | pass | passed |
| `phi-4-mini-reasoning:3.8b` | compact | 1 | 41216 | 41216 | 41.6 | pass | passed |
| `llama3.2:3b` | compact | 1 | 53760 | 53760 | 41.6 | pass | passed |
| `ministral-3:3b` | compact | 1 | 57600 | — | — | fail | failed |
| `smollm3:3b` | compact | 1 | 65536 | 65536 | 35.3 | pass | passed |
| `gemma-4:31b` | compact | 0 | 93440 | 93440 | 183.9 | pass | passed |
| `qwen3-coder:30b-a3b` | compact | 0 | 112128 | 112128 | 58.2 | pass | passed |
| `devstral-small:24b` | compact | 0 | 117504 | — | — | fail | failed |
| `mellum2.1:12b-a2.5b` | compact | 1,2 | 129280 | 129280 | 104.5 | pass | passed |
| `gemma-4:e2b-q8` | compact | 1 | 131072 | 131072 | 31.7 | pass | passed |
| `gemma-4:e4b` | compact | 1 | 131072 | 131072 | 71.5 | pass | passed |
| `gpt-oss:20b` | compact | 0 | 131072 | 131072 | 41.5 | pass | passed |
| `minicpm5:2b` | compact | 1 | 131072 | 131072 | 38.3 | pass | passed |
| `nex-n2.5:mini` | compact | 0 | 141568 | 141568 | 84.4 | pass | passed |
| `qwen3-coder-next:80b-a3b` | compact | 0,1,2,3,4,5 | 185600 | — | — | fail | failed |
| `ornith-1.5:35b-a3b` | compact | 0 | 188672 | 188672 | 71.2 | pass | passed |
| `qwen3.8:27b` | compact | 0 | 190720 | 190720 | 51.4 | pass | passed |
| `gemma-4:12b` | compact | 1,2 | 207616 | 207616 | 130.8 | pass | passed |
| `qwen3.6:27b` | compact | 0 | 208384 | 208384 | 51.5 | pass | passed |
| `qwen3.5:27b` | compact | 0 | 209664 | 209664 | 196.8 | pass | passed |
| `qwen3.6:35b-a3b` | compact | 0 | 243968 | 243968 | 74.6 | pass | passed |
| `gemma-4:26b-a4b` | compact | 0 | 262144 | 262144 | 160.8 | pass | passed |
| `qwen2.5-coder:14b` | trained_ceiling | 1,2,3 | 32768 | 32768 | 118.0 | pass | passed |
| `llama3.2:3b` | trained_ceiling | 1,2,3 | 131072 | 131072 | 41.6 | pass | passed |
| `mellum2.1:12b-a2.5b` | trained_ceiling | 1,2,3 | 131072 | 131072 | 104.4 | pass | passed |
| `phi-4-mini-reasoning:3.8b` | trained_ceiling | 1,2,3 | 131072 | 131072 | 41.7 | fail | failed |
| `devstral-small:24b` | frontier | 0,1,2,3,4,5 | 259072 | 259072 | 61.4 | pass | passed |
| `ministral-3:3b` | trained_ceiling | 0 | 262144 | 262144 | 18.6 | pass | passed |
| `ministral-3:8b` | trained_ceiling | 0,1 | 262144 | 262144 | 28.2 | pass | passed |
| `nex-n2.5:mini` | trained_ceiling | 0,1 | 262144 | 262144 | 77.9 | pass | passed |
| `ornith-1.5:35b-a3b` | trained_ceiling | 0,1 | 262144 | 262144 | 74.6 | pass | passed |
| `qwen3.6:35b-a3b` | trained_ceiling | 0,1 | 262144 | 262144 | 77.7 | pass | passed |
| `gemma-4:12b` | trained_ceiling | 1,2,3 | 262144 | 262144 | 127.7 | pass | passed |
| `ornith-1.5:9b` | trained_ceiling | 1,2,3 | 262144 | 262144 | 38.5 | pass | passed |
| `qwen3.5:27b` | trained_ceiling | 0,1,2 | 262144 | 262144 | 206.9 | pass | passed |
| `qwen3.6:27b` | trained_ceiling | 0,1,2 | 262144 | 262144 | 61.3 | pass | passed |
| `qwen3.8:27b` | trained_ceiling | 0,1,2 | 262144 | 262144 | 61.4 | pass | passed |
| `ministral-3:14b` | trained_ceiling | 0,1,2,3 | 262144 | 262144 | 38.2 | pass | passed |
| `gemma-4:31b` | trained_ceiling | 0,1,2,3,4 | 262144 | 262144 | 193.6 | pass | passed |
| `qwen3-coder:30b-a3b` | trained_ceiling | 0,1,2,3,4 | 262144 | 262144 | 74.6 | pass | passed |
| `nemotron-3.5-bolt:74b-a9b` | trained_ceiling | 0,1,2,3,4,5 | 262144 | 262144 | 206.7 | pass | passed |

Failed cases remain unpromoted; inspect their individual logs and receipts. A projected trained ceiling that fails to load needs a lower-context follow-up. Fast/slow paired speed tests are a separate step at the same context.
