# Dense 70B NVMe-path repeat

The `llama70-nvme-two-ram-chats-direct-20261108` sequence passed on
2026-11-08. It repeated the same Llama 3.3 70B Q4_K_M GGUF, GPU 0-5 split,
8K and 32K RAM chat caps, and 16-token concurrent decode as the
[shared-path run](../llama70-two-ram-chats-20261108/README.md). This time the
GGUF path was `/data/model-hotset/llama-3.3-70b/` on the rig's NVMe drive.

| Run | Stage wall time | Two-chat decode |
| --- | ---: | ---: |
| Shared path | 17m53s | 4.573569 s, 6.996724 aggregate tok/s |
| NVMe path | 3m29s | 4.495899 s, 7.117597 aggregate tok/s |

Both chats admitted and produced the same first tokens as the shared-path
run. The NVMe model was copied immediately before this repeat; Linux page
cache was not cleared. The stage times also include context setup and
inference. The comparison supports keeping active test models on NVMe, but
it is not a controlled cold-storage throughput benchmark. The successful
42,520,398,816-byte transfer and full model load are the practical copy
checks used for this experiment.

The sequence runner ran directly on the rig after three Manager launch
attempts exited with SSH code 255 before creating a run folder. Those launch
commands added an unnecessary SSH hop; the documented Manager invocation
passes the rig-side Python command with the benchmarking repo as its working
directory. The direct runner acquired its normal benchmark lease and wrote a
passed terminal receipt. The ordinary 27B chat profile was restored afterward.

Evidence: [`terminal.json`](terminal.json),
[`llama70_nvme_two_ram_chats.json`](llama70_nvme_two_ram_chats.json), and
[`llama70_nvme_two_ram_chats.log`](llama70_nvme_two_ram_chats.log).
