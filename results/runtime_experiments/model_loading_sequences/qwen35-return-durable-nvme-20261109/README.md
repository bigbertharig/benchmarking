# NVMe durable return checkpoint (2026-11-09)

Three fresh-process stages passed at 100K: commit turn 1, recover it and
commit turn 2, then recover turn 2 with byte-identical state. A ~133 MB
record took 0.518/0.524 s to checksum, write, and sync on the rig's NVMe,
versus about 2.01 s on shared storage. See the [durability result](../qwen35-return-durable-20261109/README.md)
and [parsed receipt](../qwen35-return-durable-20261109/receipt.json).
