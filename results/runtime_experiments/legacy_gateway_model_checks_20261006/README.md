# Legacy gateway model checks (2026-10-06)

These raw JSON receipts came from the retired local `llm-gateway` copy on the GPU rig (`/home/bryan/llm-gateway`, later archived as `/home/bryan/legacy-repos/llm-gateway-20261115`). They were the only files in that copy absent from the current Pi gateway tree after excluding the old virtual environment and caches. Preserved on 2026-11-15 before removing the retired copy.

- `model_check_20261006_193319.json`: coder 7B and chat 27B gateway checks, including context, streaming, tool-call, and speed observations.
- `model_check_20261006_194040.json`: a later chat 27B check on cards 0 and 2.

Historical evidence only. Use the current model registry and newer benchmark receipts for placement decisions.
