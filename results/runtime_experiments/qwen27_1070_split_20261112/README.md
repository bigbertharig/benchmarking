# Invalid pilot: GPU ordinal mismatch

These pilot timings must not be used as a 1070 comparison. Docker exposed all cards and `CUDA_VISIBLE_DEVICES=0,2,3` was interpreted in CUDA ordinal order, which differed from the host `nvidia-smi` indices. Host GPU 2 (GTX 1070) remained unused; the purported 1070 leg loaded host GPU 1 (GTX 1060). The issue was detected by comparing host VRAM deltas and llama device logs. The corrected UUID-selected, VRAM-verified run is in [qwen27_1070_split_20261112_uuid_long](../qwen27_1070_split_20261112_uuid_long/README.md).
