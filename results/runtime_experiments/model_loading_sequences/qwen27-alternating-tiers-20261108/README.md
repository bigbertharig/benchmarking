# One 27B weight load with three alternating chats

The `qwen27-alternating-tiers-20261108` sequence passed all three placement
stages on 2026-11-08. Each stage loaded the same NVMe-backed Qwen3.6 27B
Q4_K_M GGUF once, with a 15,345.66 MiB CUDA0 model buffer and a 682.03 MiB
CPU-mapped model buffer. Chat A remembered `4827`, B `6193`, and C `7358`.
The required turn order was **A → B → A → C → A**; a final B/C recall check
confirmed that A's later turns did not erase their distinct contexts. Every
recall returned its own code in visible output. Each chat had a 16,384-token
configured cap.

| Chat KV placement | Physical KV buffers | Sampled GPU memory peaks, MiB | Stage wall |
| --- | --- | --- | ---: |
| A GPU1, B GPU3, C GPU5 | 288 MiB on each named 1060 | GPU0 16,389; GPU1/3/5 439 each | 2m48s |
| A GPU1+2, B GPU3+4, C GPU5 | 144 MiB on each pair card; C 288 MiB on GPU5 | GPU0 16,389; GPU1-4 295 each; GPU5 439 | 2m42s |
| A/B/C in RAM | 288 MiB CPU KV per chat | GPU0 16,189; GPUs1-5 71 each | 1m12s |

The occupied positions after all checks were A 8,228, B 3,144, and C 6,216.
The five filler phases added 17,234 tokens in total to those three contexts.
Their aggregate fill duration was about 116.7 seconds on separate 1060s,
116.4 seconds on paired cards, and 59.0 seconds with RAM KV, roughly 148,
148, and 292 filler tokens/s respectively. The individual A final fill of
4,048 tokens ran at 133.9, 134.5, and 274.8 tokens/s. Final code-word
generation took roughly 0.4-0.5 seconds per turn. The stage wall times include
model loading and differ in cache warmth, so fill-phase timings are the more
useful matched comparison here.

The experiment confirms that adding and revisiting these chats did not reload
the weights; the log has one `MODEL_READY` per stage and distinct `ADD`/KV
allocation events. It does **not** prove that a real conversation with varied
text will have the same prefill ratio. The filler repeats a short unrelated
note, decode answers are brief, and only one chat turn executes at a time.
The pair mode assigns A to GPUs1+2, B to GPUs3+4, and C to GPU5 because five
1060s cannot form three disjoint pairs. The pair pointer takes precedence over
the printed single fallback for A. A useful next comparison is real mixed
history and simultaneous generation at the same occupied depths.

The host `MemAvailable` minimum was 28,335,800 KiB for singles, 28,333,120
KiB for pairs, and 26,997,616 KiB for RAM KV. The three stages exited 0,
the sequence terminal status is `passed`, and the ordinary 27B chat profile
was restored afterward.

Evidence: [`terminal.json`](terminal.json), stage JSON receipts in this
directory, and the raw logs and 1 Hz GPU/PCIe samples in the linked shared
experiment output paths recorded by the campaign manifest.
