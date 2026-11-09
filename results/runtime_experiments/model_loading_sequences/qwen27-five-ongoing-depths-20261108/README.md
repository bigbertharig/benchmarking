# Qwen27 five independent 1060 chats at 50K–200K

2026-11-08/09. [Campaign](../../../../campaigns/qwen27_five_ongoing_depths_20261108.json); [terminal receipt](terminal.json); [restoration receipt](restoration.json). Manager run `qwen27-five-ongoing-depths-20261108` passed, 23:59:24–00:58:55 UTC. The ordinary chat route was restored by 00:59:30 UTC. Raw log: `/mnt/shared/experiments/kv-matrix-20261107/qwen27_five_ongoing_depths_20261108.log`.

## Question and method

How quickly does each chat generate when one 27B model serves five separate 1060-resident chats, compared with one 1060 chat generating alone at the same occupied depth? Can the chats continue through 50K, 100K, 150K, and 200K positions when each new batch is prepared on the 3090 and the updated state is returned to its 1060?

One Qwen3.6 27B Q4 model loads on GPU0. Five independent contexts reserve 262,144 positions, one on each 1060 (GPUs1–5), with Q4 K/V. Each chat has its own private four-digit code. At each milestone, the harness restores the preceding chat state to a temporary GPU0 context, adds the next synthetic user turn and field-note tokens to the target occupied depth, saves the updated state, and restores it onto that chat's 1060. Each worker then recalls its private code. The harness saves each validated state in an atomic checkpoint file on shared storage. A solo 16-token generation window runs on worker1; worker1 is restored to the same saved state; then all five workers generate 16 tokens concurrently. Each depth starts from the previous checkpoint, so generation probes do not become part of the next chat turn.

The measurement reports per-chat generation tokens per second, latency distribution, and the five-chat aggregate. Preparation, state save/restore, and recall are logged separately. The direct 1060 prompt-ingestion path is intentionally omitted because previous matched tests already showed it was much slower. The model stays loaded through all four depths; the 1060 contexts remain allocated during each GPU0 preparation step.

## Results

The [true single-chat replay](../qwen27-one-checkpoint-solo-20261108/README.md) restored the exact saved worker1 states with only GPU0 and GPU1 in use, and took the median of three 16-token solo windows at each depth.

| Occupied depth | True one-chat solo | Worker1 solo, four parked | Five active chats, per-chat range | Worker1 active / true solo |
| ---: | ---: | ---: | ---: | ---: |
| 50,000 | 6.74 tok/s | 6.54 tok/s | 5.25–5.38 tok/s | 0.78× |
| 100,000 | 3.75 tok/s | 3.65 tok/s | 2.90–3.11 tok/s | 0.81× |
| 150,000 | 2.57 tok/s | 2.53 tok/s | 2.05–2.12 tok/s | 0.83× |
| 200,000 | 1.98 tok/s | 1.96 tok/s | 1.55–1.65 tok/s | 0.78× |

All 20 private-code recalls passed. Four parked chats changed worker1's solo rate by only about 1–3% relative to the true one-chat replay, within the scope of these short windows. Activating all five chats reduced worker1's per-chat rate to 78–83% of its true solo rate. Occupied context had the larger effect: true solo fell from 6.74 to 1.98 tok/s between 50K and 200K.

The added 50K tokens took about 75, 99, 123, and 146 seconds on GPU0 per worker at the four successive levels. At 200K, the saved live state was about 3.85 GB. Worker1's GPU0 state save took 1.9 seconds, restoring it on its 1060 took 9.4 seconds, and saving the answered 1060 state took 10.3 seconds. These transfer costs are outside the generation windows.

## Limits

The histories use repeated synthetic notes and a short private-code recall, rather than natural varied conversations. Sixteen-token generation windows measure local throughput near each checkpoint and may include sampling of end-of-turn tokens. GPU0 preparation is sequential across the five chats, whereas the decode probe runs all five simultaneously. The test measures GPU0 preparation while worker contexts are resident, but does not measure a separate main chat responding during preparation. A 200K occupied checkpoint is below the model's 262K context cap.
