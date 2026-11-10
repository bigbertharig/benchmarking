# Durable single-chat return checkpoint (2026-11-09)

Here, a **restart** means the inference process or Docker container ends
between turns, or the rig reboots and reloads the model. The earlier
[in-memory return-delta prototype](../qwen35-return-delta-20261109/README.md)
lost its newest chat updates when that process exited. This isolated fork
persists one base snapshot plus one record per completed turn. Each record
contains the outbound and worker-return updates together. It is written
to a unique temporary file, synced, atomically renamed, and followed by a
directory sync. Recovery replays only contiguous committed records and
ignores incomplete temporary files.

The test used Qwen3.6-35B-A3B Q4_K_XL weights on GPU0, one Q4_1 worker on
GPU1, a 262K reservation, and a validated 100K starting state. Each stage
was a new Docker process with a fresh model/context load. The first shared-
storage run committed turn 1 and deliberately left an incomplete turn 2.
Recovery restored turn 1 exactly but exposed a temporary-name collision:
Docker assigned PID 1 to both processes. The initial campaign correctly
records that failure. The corrected build gives each pending file a unique
time-based suffix; its fresh process ignored the old pending file,
committed turn 2, and another fresh process restored turn 2. Both restored
states matched full worker snapshots byte for byte.

| Checkpoint storage | Turn record | Return export | Record checksum, write, and sync | Complete measured turn |
| --- | ---: | ---: | ---: | ---: |
| Shared storage | ~133 MB | 0.036–0.037 s | **2.01–2.02 s** | 3.48–3.51 s |
| Rig NVMe | ~133 MB | 0.036 s | **0.518–0.524 s** | 1.99–2.05 s |

The NVMe result passed two fresh-process turns and a third-process exact
state check. It retains much of the benefit over the earlier 100K full
1060 capture path (about 3.31/2.83 s for two short turns), while paying
for a durable write after each answer. These complete-turn timings start
after model load and checkpoint recovery. The initial base copy, model
load, full-state verification snapshots, and process startup are separate
costs. The test-only `expected-*.bin` files are full snapshots used for
byte comparison; the operational checkpoint consists of `base.bin` and
`turn-*.bin` records.

## Recovery guards

- A fresh process recovered from a base with **zero** committed records
  and committed its first turn.
- A deliberately incomplete turn-2 `.pending` file was ignored while the
  prior committed turn remained recoverable.
- A copied committed record with one changed payload byte was rejected
  with `DURABLE_REJECT reason=checksum` (expected exit 75). The real
  checkpoint was not modified.

The record checks its payload checksum, base-snapshot identity, model file
size, Q4_1 KV type, context capacity, and contiguous turn number. The
base loader validates the base snapshot's own checksum and model state.
This does **not** rehash the model weights on every turn. A damaged
committed record stops recovery rather than silently skipping a turn;
automatic repair/rollback is not implemented.

This is a benchmark prototype, not a production manager loader. A real
server must commit the return record **before** treating the answer as
delivered, and define retry behavior if it stops between generation and
commit. The on-disk journal still grows by about 133 MB per turn; the
[in-memory compaction test](../qwen35-return-delta-20261109/README.md#checkpoint-growth-and-compaction)
does not yet provide atomic on-disk compaction. The tests cover process
restarts and filesystem sync calls, not a forced rig or storage-server
power loss. File-size/model metadata guards are useful but do not prove
cryptographic model identity.

Evidence: [parsed receipt](receipt.json), [source patch](durable_return.patch),
[build recipe](build.sh), [initial shared campaign](../../../../campaigns/qwen35_return_durable_20261109.json),
[corrected recovery campaign](../../../../campaigns/qwen35_return_durable_resume_fix_20261109.json),
[NVMe campaign](../../../../campaigns/qwen35_return_durable_nvme_20261109.json),
and [guard campaign](../../../../campaigns/qwen35_return_durable_guards_20261109.json).
Stage and terminal receipts are in the corresponding campaign result folders;
raw logs are under `/mnt/shared/experiments/kv-matrix-20261107/`.
