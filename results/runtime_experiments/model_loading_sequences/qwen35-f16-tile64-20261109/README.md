# F16 attention 64-thread control (2026-11-09)

The single-1060 F16 replay changed the NVIDIA FP32 fallback head-256,
eight-column tile from the normal 256-thread block to 64 threads. Bracketed
16K/32K/50K controls were stable near 69/60/50 tok/s; the candidate reached
53.25/40.03/30.61 tok/s. The traced 50K attention kernel took 1,429.9 ms
over 64 tokens, versus 631.9 ms on the unchanged build. This is a clear
regression. See the [comparison](../qwen35-f16-tile128-20261109/) for scope
and interpretation.
