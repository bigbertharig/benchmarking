# bench-runtime

Measures operational behavior of an already-running llama-compatible runtime:

- repeated-request stability
- streaming time to first token
- prompt/generation throughput when exposed by the runtime
- controlled context growth
- optional peak VRAM, GPU-seconds, and energy telemetry through `nvidia-smi`

The quality score for each test is request success rate. Latency, throughput,
memory, GPU time, and energy remain separate efficiency fields; they are not
collapsed into an invented overall score.

Build and run on the GPU rig:

```bash
cd /mnt/shared/plans/shoulders/benchmarking/docker/bench-runtime
docker build -t bench-runtime .

docker run --rm --network host --gpus 'device=1' \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-runtime/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-runtime \
  --model qwen3.5:4b \
  --runtime-base http://localhost:11435 \
  --gpu-ids 1 \
  --hardware-id rig-gpu1-gtx1060-6gb \
  --run-name qwen35_4b_runtime_v1 \
  --run-class provisional
```

`--hardware-id` is required so latency and cost records cannot become
hardware-ambiguous. Omit `--gpu-ids` for endpoint-only measurement. When GPU IDs are requested,
missing `nvidia-smi` telemetry is a hard preflight failure rather than silently
producing zero memory or energy values.

The historical `context_window_benchmark.py` reports remain valid. This suite
adds canonical-ledger recording and broader operational signals; it does not
rewrite those older reports.
