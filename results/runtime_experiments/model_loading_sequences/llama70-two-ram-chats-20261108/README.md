# Dense 70B with two RAM chats

The `llama70-two-ram-chats-20261108` sequence passed on 2026-11-08. It used
one Llama 3.3 70B Q4_K_M model load across GPUs 0-5 and added two independent
CPU KV contexts. The model came from shared storage for this first run.

| Allocation | Result |
| --- | ---: |
| GPU0 model buffer | 19,059.88 MiB |
| GPU1, GPU2, GPU3 model buffer | 4,317.00 MiB each |
| GPU4 model buffer | 4,033.38 MiB |
| GPU5 model buffer | 3,935.23 MiB |
| Chat A | 8K cap, 720 MiB CPU KV |
| Chat B | 32K cap, 2,880 MiB CPU KV |

Both chats admitted and produced a first token. Their concurrent decode of 16
tokens each took 4.573569 seconds, 6.996724 aggregate tokens/s. The stage ran
from 05:36:55 to 05:54:48 UTC (17m53s), including shared-storage model loading,
context setup, and inference. Host `MemAvailable` fell from 29,939,904 to a
minimum of 26,159,056 KiB during the stage. The test used short prompts, so
the 8K and 32K figures are configured ceilings, not occupied history sizes.

This proves distinct CPU KV allocations and simultaneous decode on a single
large-model load. It does not yet test deep history, chat reopening, or NVMe
load time. A local NVMe copy of the same GGUF is the next load-path probe.

Evidence: [`terminal.json`](terminal.json),
[`llama70_two_ram_chats.json`](llama70_two_ram_chats.json), and
[`llama70_two_ram_chats.log`](llama70_two_ram_chats.log).
