# Qwen 35B Q4 worker context and saturation tests — 2026-11-18

This validates the production `shared_kv_http_v1` topology for
`qwen3.6:35b-a3b-xl`: shared weights and the 262,144-token main chat on GPU0,
with dynamically attached Q4 worker contexts on four 6 GiB GTX 1060s and one
8 GiB GTX 1070. The measured service instance was
`c0b0afe0a0bf445d81bb66dc040ecda4`.

## Context allocation curve

Each row attached a fresh worker to GPU5, generated a labeled short response,
detached it, and verified return to baseline.

| Context cap | Worker allocation MiB | Decode tok/s |
| ---: | ---: | ---: |
| 16,384 | 124 | 75.40 |
| 32,768 | 246 | 76.66 |
| 51,200 | 384 | 78.09 |
| 102,400 | 768 | 92.64 |
| 153,600 | 1,148 | 91.74 |
| 204,800 | 1,530 | 94.18 |
| 256,000 | 1,914 | 93.42 |
| 262,144 | 1,958 | 94.28 |

The worker allocation is effectively linear: `ceil(1958 * context / 262144)`
MiB. The older estimate of about 1 GiB fixed compute plus 1 GiB KV per chat
was not observed; the full 1,958 MiB is context-dependent allocation.

## Normal concurrency and placement

Two full contexts on separate 1060s decoded at 44.37 and 43.33 tok/s. Three
separate full contexts decoded at 61.22, 45.23, and 54.93 tok/s. Two full
contexts stacked on one 1060 decoded at 41.15 and 46.77 tok/s, so Qwen's
same-card stacking penalty is much smaller than Nemotron's. A realistic mixed
32K/100K/200K workload on three cards decoded at 55.13, 58.44, and 60.33 tok/s.

The production controller also passed mixed-size attach, receipt, pooled-claim,
partial detach, final claim release, and baseline recovery checks.

## Safety-governed saturation

The first saturation attempt exposed two admission-accounting issues rather
than a usable capacity result. `memory.total - memory.used` overstated actual
free memory by about 451 MiB on the RTX 3090 Ti and 84 MiB on the GTX 1070.
After switching admission to NVIDIA's direct `memory.free`, nine idle children
left 262 MiB free on GPU0, but their first concurrent turns retained another
about 182 MiB of runtime state and reduced free memory to 80 MiB. No OOM
occurred, and the excess children were detached immediately.

The corrected policy reserves 416 MiB on the parent before admitting another
Qwen child, reserves 74 MiB of measured parent state per attached child, and
reserves 272 MiB idle on each worker card so the observed first-turn increase
still leaves at least 256 MiB active. It admits six full 262,144-token
children and rejects a seventh even when the requested worker context is only
16K. Six concurrent labeled turns all passed at 21.65-36.97 tok/s per chat;
GPU0 bottomed at 298 MiB free, above the 256 MiB operational floor.

The safe production maximum is therefore six attached Qwen chats on a freshly
started service. Parent-side state is the limiting resource before worker-card
KV capacity, so smaller contexts cannot safely fill the remaining worker-card
gaps after six children. A service that has already generated and released
children may report five immediately available slots because retained runtime
allocations are reflected in live `memory.free`; that conservative live result
is intentional.

## Headless worker-pool mode

The server was then restarted without a GPU0 conversation context. It retained
the shared Qwen weights but exposed only dynamically attached worker chats.
GPU0 free memory increased from about 0.8-0.9 GiB in main-chat mode to 3.06 GiB
at fresh headless startup, so parent-side state stopped limiting the pool.

The headless service admitted 11 full 262,144-token chats: two on each 6 GiB
1060 and three on the 8 GiB 1070. It then admitted four 240,000-token gap-fill
chats on the 1060s and one 249,000-token gap-fill chat on the 1070. A
seventeenth request at the minimum 16K capacity was rejected.

All 16 chats generated concurrently and returned their exact labels. Decode
rates were 12.77-37.89 tok/s per chat. During generation GPU0 retained at least
1,402 MiB free, the 1060s retained at least 272 MiB, and the 1070 retained 262
MiB. All children detached, all pooled worker claims released, and every worker
card returned to baseline. This validates a distinct `gpu0-worker-pool-q4`
production mode with 11 full contexts or 16 chats in the measured mixed-cap
layout; it does not provide a local main-chat route.
