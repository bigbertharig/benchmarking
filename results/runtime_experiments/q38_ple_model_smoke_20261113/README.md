# Qwen3.8 PLE table on Pascal VRAM: model smoke (2026-11-13)

An isolated patched llama.cpp server tested the same Qwen3.8 Flash-Next UD-Q4_K_XL GGUF and 16-token prompt twice: the ordinary file-backed PLE path, then a plugin that stores exact IQ4_NL table rows across the GTX 1070 and four GTX 1060s. Eight model layers were assigned to GPU0 (RTX 3090 Ti); the remaining model weights used llama.cpp's mmap path. Context was 8192. The test ran under a 28 GiB container limit and a 4 GiB host `MemAvailable` guard.

| Mode | PLE in Pascal VRAM | Startup | Prompt tokens/s | Generated tokens/s | Output |
| --- | ---: | ---: | ---: | ---: | --- |
| File-backed control | 0 | 163.42 s | 0.635 | 0.851 | identical |
| Five Pascal GPUs | 28,800,138,240 bytes; all 320,001,536 rows | 298.12 s | 0.604 | 0.876 | identical |

The GPU path allocated 7,516,192,680 table bytes on the 1070, 5,368,709,070 bytes each on three 1060s, and 5,177,818,350 bytes on the fourth 1060. It left zero table rows on file. The 3090 held about 13.5 GiB of model/runtime state at request time. Host `MemAvailable` stayed above 27.5 GiB in both modes. The managed run passed and released its claim.

This is one short, cache-sensitive smoke, not a precise speed comparison. The 2.97% generated-token difference is too small to distinguish from run variation. The table transfer added roughly 135 seconds to startup. The model is slow in both modes because this configuration still pages non-offloaded weights; moving only the table does not create a bounded RAM expert cache or change routed-expert execution. The installed Strata binary is not patched by this llama.cpp experiment.

The lookup already has a central range directory: `(first_row, row_count, device)` per shard. It selects one card by row number and copies the selected packed row; no cross-card search occurs. The next performance probe should isolate synchronous small PCIe transfers, batch requests per destination where possible, and measure hot-row reuse before allocating a 3090 cache. A later combined test needs explicit expert RAM capacity and NVMe miss policy.

Read-only `lspci -vv` after the run showed the GGUF's `/data` NVMe device at a negotiated 5 GT/s x1, while each Pascal card showed 2.5 GT/s x1. The Pascal cards sit behind a PCIe switch and may share upstream bandwidth. These are observed link states, not measured sustained transfer rates. File-backed mmap may serve rows from host page cache; neither the 0.85 nor 0.88 tokens/s figure isolates a cold physical NVMe read or the PLE lookup cost.

The first managed smoke attempt failed before model load because the test container lacked `LD_LIBRARY_PATH`; [its terminal receipt](../model_loading_sequences/q38-ple-model-smoke-20261113/terminal.json) records that setup failure. The [successful managed receipt](../model_loading_sequences/q38-ple-model-smoke-v2-20261113/terminal.json), [mode timings](terminal.json), [runner](../../../scripts/integration/run_q38_ple_model_smoke.py), [campaign](../../../campaigns/q38_ple_model_smoke_20261113.json), [source patch](../../../scripts/integration/patch_qwen4exp_ple.py), [GPU store](../../../scripts/integration/ple_shard_store.cu), and [build script](../../../scripts/integration/build_ple_shard_runtime.sh) preserve the result. Server logs are `file.log` and `gpu.log` here. The isolated rig build is `/data/bench-staging/ple-shard-llama-build-20261113`.
