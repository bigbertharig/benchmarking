# Nemotron F16 worker context-capacity sweep — 2026-11-18

This measures the production `shared_kv_http_v1` topology: Nemotron 3.5 Bolt
74B A9B UD-Q3_K_XL weights on GPU0, whole experts on GPUs1-4, the 262,144-token
main F16 context on GPU0, and one fresh F16 worker context on GPU5. The service
instance was `10f6faa879d84895bfa8f083411e9252`.

Each row started from main-only, recorded GPU5 memory, attached a fresh chat at
the named capacity, generated a labeled short answer, detached it, and verified
that GPU5 returned to its baseline. All eight rows passed and the final service
again contained only `main`.

| Context cap | GPU5 allocation delta MiB | Attach s | Decode tok/s | Answer |
| ---: | ---: | ---: | ---: | --- |
| 16,384 | 130 | 0.159 | 37.81 | `CTX-16384` |
| 32,768 | 258 | 0.109 | 38.22 | `CTX-32768` |
| 51,200 | 402 | 0.111 | 37.95 | `CTX-51200` |
| 102,400 | 802 | 0.112 | 41.00 | `CTX-102400` |
| 153,600 | 1,204 | 0.112 | 41.44 | `CTX-153600` |
| 204,800 | 1,604 | 0.121 | 41.72 | `CTX-204800` |
| 256,000 | 2,006 | 0.122 | 41.42 | `CTX-256000` |
| 262,144 | 2,054 | 0.126 | 41.89 | `CTX-262144` |

The allocation curve is effectively `context_tokens / 128 MiB`, plus a small
2-6 MiB observed overhead. A production reservation must still add an explicit
admission margin rather than treating the sampled delta as the limit.

## Stacking and multi-card admission follow-up

The 2026-11-18 follow-up enabled same-card contexts behind a probe flag, then
deployed the measured policy through Orchestration. Two 262,144-token contexts
on GPU5 used 4,178 MiB before turns and 4,190 MiB after turns. Concurrent decode
was about 19 tokens/s per chat, versus about 42 tokens/s for one chat.

With those two max contexts resident, a third context passed at every tested
capacity and returned to the 4,190 MiB baseline after detach:

| Third context cap | Peak GPU5 MiB | Concurrent replies |
| ---: | ---: | :--- |
| 16,384 | 4,320 | pass |
| 51,200 | 4,592 | pass |
| 102,400 | 4,992 | pass |
| 153,600 | 5,394 | pass |
| 204,800 | 5,794 | pass |

Spreading two 200K contexts across physical GPU1 and GPU5 produced about 31.2
and 30.8 tokens/s concurrently (about 62 aggregate), materially better than
stacking two contexts on GPU5. Four distributed contexts produced 75-79
aggregate tokens/s. A fifth child failed because its fixed recurrent-state
allocation exhausted GPU0, despite capacity on its KV card. The production
policy therefore reserves 182 MiB of shared GPU0 state per child and caps this
topology at four attached children.

Production instance `33ae9673c3834a8d8c913d3cf90f95f0` then validated the
complete controller path: two max contexts plus two 200K contexts, fifth-child
pre-admission rejection, spread-first placement, same-card fallback on GPU5,
one pooled GPU5 claim, live occupancy receipts, detach, claim release, and full
return to main-only card baselines.

This validates variable context reservation, same-card stacking, multi-card
placement, concurrent short replies, cumulative-memory admission, and cleanup.
Deep occupied-token quality remains a separate long-context test.

The reusable runner is `scripts/active/nemotron_http_context_sweep.py`.
