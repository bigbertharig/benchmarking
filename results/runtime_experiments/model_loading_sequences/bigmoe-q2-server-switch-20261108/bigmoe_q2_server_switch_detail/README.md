# BigMoe Q2 server conversation switching

The `bigmoe-q2-server-switch-20261108` sequence passed on 2026-11-08.
BigMoe v0.40.1's HTTP server loaded the NVMe-backed Qwen3.8 Flash Next Q2
model once with CPU/flash expert streaming and an 8 GiB expert cache. It
listened only on `127.0.0.1`. The ordinary GPU0 27B chat profile remained
loaded (sampled GPU0 use 23,617 MiB before and after). Server readiness took
240.2 seconds; host `MemAvailable` stayed above 16,057,136 KiB.

Four OpenAI-compatible, full-history chat requests ran in order A → B → A → A.
All returned the expected independent code word. A first returned `ORCHID`,
B first `LANTERN`, A reopened `ORCHID`, and A continued `ORCHID`.

| Request | `n_prompt` actually prefilled | `n_past` | Prefill seconds | Request wall seconds | Cumulative expert cache hit |
| --- | ---: | ---: | ---: | ---: | ---: |
| A first | 23 | 26 | 14.23 | 16.42 | 17.8% |
| B first | 23 | 26 | 2.67 | 3.95 | 54.2% |
| A reopened after B | 48 | 51 | 7.19 | 8.43 | 64.1% |
| A continued immediately | 22 | 76 | 4.37 | 5.40 | 68.0% |

The reopened A request sent A's full history and processed 48 prompt tokens.
The immediate next A request processed only its new suffix (22 tokens).
Combined with B's reset to `n_past=26`, this is evidence that the HTTP server
has one live KV stream and recomputes a switched conversation's prefix, while
the loaded weights and expert cache persist. It does not demonstrate separate
resident KV states for A and B. The prompts were short and the cache warmed
through the sequence, so the wall times are not a fair comparison of long-chat
switching costs. A larger-history replay or explicit KV snapshot/restore is
the next useful test.

Evidence: [`terminal.json`](terminal.json), four saved response JSON files,
[`events.txt`](events.txt), and server stdout/stderr files in this directory.
The outer sequence receipt is [`../terminal.json`](../terminal.json).
