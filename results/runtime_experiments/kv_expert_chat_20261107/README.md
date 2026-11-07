# Nemotron expert tensors with per-chat 1060 caches (2026-11-07)

This experiment combines the [Nemotron whole-expert placement sweep](../nemotron_expert_sweep_20261106/README.md)
with the [per-chat cache prototype](../kv_overnight_20261107/README.md). It
tests whether the previously observed expert-placement speedup survives while
two or three independent chat contexts keep their KV/state on GTX 1060s.

The model is the same Nemotron 3.5 Bolt 74B UD-Q3_K_XL GGUF in every row.
The private b11669 llama.cpp build adds an environment-selected per-context
GPU cache and a generic text-file interface to llama.cpp tensor buffer
overrides. The file contains one physical GPU index and one tensor-name regex
per tab-separated line. The expert groups are the four matched groups from
the earlier sweep. The model, prompt, greedy sampler, Q4 K/V, context limits,
three chat assignments, and output count remain fixed within a comparison.

Chat layout: worker4 has an 8K cache on GPU4, worker5 has an 8K cache on GPU5,
and a third context with 131K configured capacity is added across GPUs4+5.
The first phase continues two chats concurrently; the second continues all
three. Each chat generates 256 timed tokens. All three histories are short,
so this measures live concurrency and capacity allocation rather than 131K
occupied-depth behavior. An additional matched run fills the two 8K chats
and a 32K paired chat to 10% and 90% with synthetic tokens, then times 128
concurrent tokens per chat at each depth.

The published four-card layer-split control uses GPUs0-3 with split
`56,16,9,8`; the five-card layer control uses GPUs0-4 with split
`56,12,11,10,10`. The expert layouts keep non-overridden weights on GPU0
and place four groups of whole routed expert tensors on GPUs1-4 or GPUs1-3
plus GPU5. Both expert placements use split `88,0,0,0,0` for their selected
model devices. The fifth 1060 is a chat-only card in each expert layout.

The per-chat cache and tensor override combination is experimental code,
not a Manager serving profile. CUDA model buffer placement, first tokens,
per-chat and aggregate rates, memory samples, and PCIe samples are archived
with the run. Short capital prompts give a basic output check but are not a
quality benchmark. The 131K paired context is allocated, not filled.

## Results

All four short-history runs exited 0, loaded the weights once, created three
contexts, and emitted the same three first-token answers (Tokyo, Berlin,
Ottawa). Aggregate tokens/s over 256 generated tokens per chat:

| Weight layout | Two 8K chats | Two 8K plus one 131K-capacity split chat |
| --- | ---: | ---: |
| Layers on GPUs0-3 | 27.28 | 33.09 |
| Layers on GPUs0-4 | 21.21 | 21.34 |
| Expert tensors on GPUs1-4, other weights on GPU0 | 67.13 | 72.02 |
| Expert tensors on GPUs1-3 and GPU5, other weights on GPU0 | 66.12 | 71.32 |

Against the same-five-card layer control, expert placement was 3.16x faster
for two chats and 3.37x for three. Moving the fourth expert group from GPU4
to GPU5 changed throughput by about 1-2%, small enough that this single pass
does not establish a card-choice winner. The extra-card layer control was
slower than the four-card layer baseline, so the expert gain cannot be
explained by using more weight cards alone. These phases have short occupied
histories; they do not establish the same gain at deep cache occupancy.

The depth controls used two 8K chats and one 32K paired chat. Each phase
continued all three chats for 128 timed tokens after synthetic filling.
At 10%, the small chats held 819 tokens and the paired chat 3,276; at 90%,
they held 7,372 and 29,491. Both depth runs exited 0 and passed their
concurrent phases.

| Five weight cards | 10% aggregate tok/s | 90% aggregate tok/s | Paired chat at 90% tok/s |
| --- | ---: | ---: | ---: |
| Layer split | 16.40 | 8.61 | 2.87 |
| Whole-expert split | 44.55 | 14.52 | 4.84 |
| Expert / layer ratio | 2.72x | 1.69x | 1.69x |

The expert gain persists with occupied caches, but narrows as attention and
cache work take more of each token's time. The 32K paired chat's 90% fill
took 652.4 seconds with layer splitting and 538.7 seconds with expert
placement. This is a single synthetic-history run per layout, so the
decode comparison is stronger than a general claim about prefill.

Peak sampled GPU4 use in the short-history 131K-capacity case was 5,968 MiB
for the five-card layer split and 4,638 MiB for expert placement. Thus the
layer layout had only 176 MiB of the card's 6,144 MiB nominal memory left,
while the expert layout had 1,506 MiB. The four-card layer baseline peaked
at 22,701 MiB on GPU0, versus 21,491 MiB for the expert layout. The latter
has more headroom on both the shared chat card and GPU0 in these runs.

The 1 Hz PCIe samples are preserved, but their phase timing is not precise
enough to claim fewer transferred bytes. The measured speedup is consistent
with the earlier expert sweep: non-expert layers stay on the fast 3090 while
whole routed expert tensors use the 1060s. Dense models have no routed
experts to place; their cache-placement bottleneck needs separate work.
