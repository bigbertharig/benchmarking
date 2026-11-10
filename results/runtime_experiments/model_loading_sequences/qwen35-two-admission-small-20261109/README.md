# Two-chat F16 admission paths at 16K, 32K, and 50K

The guarded `qwen35-two-admission-small-20261109` sequence passed all three
arms on 2026-11-10 UTC. Each arm loaded the same NVMe Qwen3.6-35B-A3B
Q4_K_XL weights on RTX 3090 GPU0, then admitted two independent chats in
order. Final chat KV was F16 with 262,144 reserved positions per GTX 1060.
Direct and RAM paths placed chats on GPUs1+2; the dedicated helper path
used GPU1 for temporary GPU0+GPU1 preparation and placed chats on GPUs2+3.
GPU0 had no resident chat. Both chats passed private-code recall at every
depth. Model cold load is outside the times below.

At 16K each path built the same prompt and field-note pattern from scratch.
At 32K and 50K each restored the same validated prior-depth F16 checkpoint
before adding the next history segment. The checkpoints were read from NVMe;
read/restore is included in admission. Each depth allocated fresh final
worker contexts. Before admitting the secondary chat, the main chat
generated 512 tokens solo. After restoring its starting state, another
512-token main-chat window ran during the beginning of secondary
preparation. A final 512-token window ran on both workers together.

## Readiness

`First ready` is measured from the start of that depth's first admission.
`Both ready` is elapsed time from the same start through secondary admission;
it **includes** the solo generation window and main-state save/restore
between admissions. For just the sequential admission work, sum the two
per-chat `usable_s` values in [summary.json](summary.json).

| Path | Depth | First ready | Both ready |
| --- | ---: | ---: | ---: |
| Direct worker fill | 16K | 62.6 s | 134.5 s |
| GPU0 + RAM prep | 16K | **39.4 s** | **88.5 s** |
| GPU0 + GPU1 helper | 16K | 43.6 s | 95.7 s |
| Direct worker fill | 32K | 91.4 s | 195.9 s |
| GPU0 + RAM prep | 32K | **61.7 s** | **136.3 s** |
| GPU0 + GPU1 helper | 32K | 62.3 s | 136.8 s |
| Direct worker fill | 50K | 127.0 s | 270.8 s |
| GPU0 + RAM prep | 50K | 89.0 s | 194.4 s |
| GPU0 + GPU1 helper | 50K | **80.9 s** | **175.8 s** |

## Main-chat generation during admission

These are 512-token windows in tok/s. `During` overlaps only the **early
part** of the secondary preparation, not its entire duration. The main
state was restored before each window; both-ready rates for the two chats
are in [summary.json](summary.json).

| Path | Depth | Main solo | Main during secondary prep | Main with both ready |
| --- | ---: | ---: | ---: | ---: |
| Direct worker fill | 16K | 77.3 | 57.1 | 62.8 |
| GPU0 + RAM prep | 16K | 77.1 | 59.2 | 62.9 |
| GPU0 + GPU1 helper | 16K | 77.2 | 52.2 | 64.5 |
| Direct worker fill | 32K | 60.5 | 49.4 | 56.2 |
| GPU0 + RAM prep | 32K | 60.5 | 53.5 | 59.8 |
| GPU0 + GPU1 helper | 32K | 60.3 | 46.4 | 60.6 |
| Direct worker fill | 50K | 49.9 | 46.4 | 49.3 |
| GPU0 + RAM prep | 50K | 49.8 | 45.9 | 49.5 |
| GPU0 + GPU1 helper | 50K | 49.8 | **30.6** | 49.7 |

The helper's 50K secondary admission was 18.6 seconds faster to both-ready
than RAM, but main-chat speed during its 512-token overlap fell about 39%
from solo, compared with about 8% for RAM. This is a real measured
contention window, not yet a full-turn or full-admission interference
curve. The helper's 16K and 32K overlap windows were slower too. After
both chats were resident, per-chat decode at 50K was about 49-50 tok/s
on all paths; changing preparation placement did not give a sustained
worker decode gain.

## Placement and limits

Sampled GPU-memory peaks (MiB; one-second samples may miss spikes):

| Path | GPU0 | GPU1 | GPU2 | GPU3 |
| --- | ---: | ---: | ---: | ---: |
| Direct | 21,381 | 5,217 | 5,217 | 71 |
| RAM | 21,437 | 5,215 | 5,215 | 71 |
| Helper | 21,923 | 643 | 5,217 | 5,215 |

The helper reserves GPU1 and leaves four 1060s for chats; direct and RAM
paths leave five. The paths differ in temporary KV reservation and batch
settings: direct uses the 262K worker context with batch 64 and ubatch 32;
RAM and helper use right-sized temporary contexts with batch 512 and
ubatch 32. This is a comparison of complete workflows, not a raw bandwidth
test of x1 PCIe versus RAM. The helper also uses a different worker-card
pair, so small post-admission differences may reflect card or run
variation. The earlier 100K → 150K one-chat helper win is a separate
depth and workload; these small-depth results do not contradict it.

At these depths, RAM is the better measured choice when a main chat is
active. The 50K helper saves some admission time, but its main-chat
interference needs a repeat with a longer, full-admission generation trace
before choosing it for live service. Keep tests within 16K/32K/50K for
that follow-up.

Evidence: [terminal receipt](terminal.json), [summary](summary.json),
[campaign](../../../../campaigns/qwen35_two_admission_16k32k50k_20261109.json),
[source patch](two_admission.patch), [build recipe](build.sh), and each
stage receipt in this directory. Raw logs and one-second GPU/PCIe samples
are under `/mnt/shared/experiments/kv-matrix-20261107/` with prefix
`qwen35_two_admission_{direct,ram,helper}_16k32k50k_20261109`.
