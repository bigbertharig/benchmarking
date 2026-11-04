# Context sizing pass

Manager min/max fit and load/unload checks. No chat or recall probes.
The compact case uses the fewest selected preferred-pool GPUs; max is the largest manager-suggested context on that set.
The ceiling/frontier case uses the selected larger GPU set. Model library changes require depth validation.

| Model | Target | GPUs | Planned ctx | Suggested ctx | Load s | Full offload | Status |
|---|---|---|---:|---:|---:|---|---|
| ministral-3:8b | compact | 1 | 9216 | 9216 | 35.2 | 35/35 | passed |
| phi-4:14b | compact | 1,2 | 16384 | 16384 | 54.8 | 41/41 | passed |
| qwen2.5-coder:14b | compact | 1,2 | 20224 | 21504 | 117.7 | 49/49 | passed |
| ornith-1.5:9b | compact | 1 | 25344 | 24320 | 38.5 | 34/34 | passed |
| qwen2.5-coder:7b | compact | 1 | 32768 | 32768 | 31.6 | 29/29 | passed |
| ministral-3:14b | compact | 1,2 | 34304 | 33792 | 51.5 | 41/41 | passed |
| nemotron-3.5-bolt:74b-a9b | compact | 0,1,2,3 | 35584 | 96256 | 193.6 | 89/89 | passed |
| phi-4-mini-reasoning:3.8b | compact | 1 | 41216 | 41216 | 38.3 | 33/33 | passed |
| llama3.2:3b | compact | 1 | 53760 | 53760 | 41.6 | 29/29 | passed |
| ministral-3:3b | compact | 1 | 57600 | 57600 | 21.8 | 27/27 | passed |
| smollm3:3b | compact | 1 | 65536 | 65536 | 35.0 | 37/37 | passed |
| gemma-4:31b | compact | 0 | 93440 | 93440 | 216.7 | 61/61 | passed |
| qwen3-coder:30b-a3b | compact | 0 | 112128 | 112128 | 58.1 | 49/49 | passed |
| devstral-small:24b | compact | 0 | 117504 | 117504 | 48.1 | 41/41 | passed |
| mellum2.1:12b-a2.5b | compact | 1,2 | 129280 | 129280 | 104.4 | 29/29 | passed |
| gemma-4:e2b-q8 | compact | 1 | 131072 | 131072 | 31.7 | 36/36 | passed |
| gemma-4:e4b | compact | 1 | 131072 | 131072 | 71.8 | 43/43 | passed |
| gpt-oss:20b | compact | 0 | 131072 | 131072 | 41.5 | 25/25 | passed |
| minicpm5:2b | compact | 1 | 131072 | 131072 | 35.0 | 43/43 | passed |
| nex-n2.5:mini | compact | 0 | 141568 | 141568 | 77.8 | 41/41 | passed |
| qwen3-coder-next:80b-a3b | compact | 0,1,2,3,4,5 | 185600 | 185600 | 236.0 | 49/49 | passed |
| ornith-1.5:35b-a3b | compact | 0 | 188672 | 188672 | 71.5 | 42/42 | passed |
| qwen3.8:27b | compact | 0 | 190720 | 190720 | 54.9 | 66/66 | passed |
| gemma-4:12b | compact | 1,2 | 207616 | 207616 | 127.4 | 49/49 | passed |
| qwen3.6:27b | compact | 0 | 208384 | 208384 | 51.4 | 65/65 | passed |
| qwen3.5:27b | compact | 0 | 209664 | 209664 | 193.5 | 65/65 | passed |
| qwen3.6:35b-a3b | compact | 0 | 243968 | 243968 | 77.8 | 41/41 | passed |
| gemma-4:26b-a4b | compact | 0 | 262144 | 262144 | 160.5 | 31/31 | passed |
| qwen2.5-coder:14b | trained_ceiling | 1,2,3 | 32768 | 32768 | 114.3 | 49/49 | passed |
| llama3.2:3b | trained_ceiling | 1,2,3 | 131072 | 131072 | 41.6 | 29/29 | passed |
| mellum2.1:12b-a2.5b | trained_ceiling | 1,2,3 | 131072 | 131072 | 104.4 | 29/29 | passed |
| phi-4-mini-reasoning:3.8b | trained_ceiling | 1,2,3 | 131072 | 131072 | 38.4 | 33/33 | passed |
| devstral-small:24b | frontier | 0,1,2,3,4,5 | 259072 | 259072 | 61.3 | 41/41 | passed |
| ministral-3:3b | trained_ceiling | 0 | 262144 | 262144 | 18.6 | 27/27 | passed |
| ministral-3:8b | trained_ceiling | 0,1 | 262144 | 262144 | 28.2 | 35/35 | passed |
| nex-n2.5:mini | trained_ceiling | 0,1 | 262144 | 262144 | 77.8 | 41/41 | passed |
| ornith-1.5:35b-a3b | trained_ceiling | 0,1 | 262144 | 262144 | 75.4 | 42/42 | passed |
| qwen3.6:35b-a3b | trained_ceiling | 0,1 | 262144 | 262144 | 77.8 | 41/41 | passed |
| gemma-4:12b | trained_ceiling | 1,2,3 | 262144 | 262144 | 127.5 | 49/49 | passed |
| ornith-1.5:9b | trained_ceiling | 1,2,3 | 262144 | 262144 | 41.5 | 34/34 | passed |
| qwen3.5:27b | trained_ceiling | 0,1,2 | 262144 | 262144 | 203.6 | 65/65 | passed |
| qwen3.6:27b | trained_ceiling | 0,1,2 | 262144 | 262144 | 61.3 | 65/65 | passed |
| qwen3.8:27b | trained_ceiling | 0,1,2 | 262144 | 262144 | 61.2 | 66/66 | passed |
| ministral-3:14b | trained_ceiling | 0,1,2,3 | 262144 | 262144 | 41.6 | 41/41 | passed |
| gemma-4:31b | trained_ceiling | 0,1,2,3,4 | 262144 | 262144 | 193.5 | 61/61 | passed |
| qwen3-coder:30b-a3b | trained_ceiling | 0,1,2,3,4 | 262144 | 262144 | 77.8 | 49/49 | passed |
| nemotron-3.5-bolt:74b-a9b | trained_ceiling | 0,1,2,3,4,5 | 262144 | 262144 | 203.1 | 89/89 | passed |
