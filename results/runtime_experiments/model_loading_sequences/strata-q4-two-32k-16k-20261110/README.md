# Qwen3.8 Q4: two 32K chat slots at 15K occupied (2026-11-10)

One verified Unsloth UD-Q4_K_XL Qwen3.8 Flash-Next GGUF bundle (111.3 GB) and its existing Strata pack were loaded from the rig NVMe. Strata engine 0.1.56 ran on GPU0 (3090 Ti) with an 8 GiB resident expert budget, 768 MiB VRAM reserve, INT8 KV, 32,768 context, two slots reserved at launch, MTP and drafting off, and no 1060 compute. The [campaign](../../../../campaigns/strata_q4_two_32k_slots_16k_20261110.json) extended the existing guarded two-chat probe with 1,000 filler lines per chat. Both chats were opened sequentially on one model load and then interleaved; chat A's private code was ORCHID and B's was LANTERN.

| Phase | Prompt tokens | Correct code | Wall seconds | Reported decode tok/s | Cached prompt tokens |
| --- | ---: | :---: | ---: | ---: | ---: |
| A first | 15,084 | yes | 246.55 | 3.0 | 0 |
| A warm continuation | 15,117 | yes | 16.06 | 4.8 | 15,079 |
| B first | 15,084 | yes | 236.00 | 4.4 | 0 |
| A after B | 15,117 | yes | 5.47 | 9.5 | 15,112 |
| B after B | 15,117 | yes | 6.88 | 19.9 | 15,079 |

The model load took 203.57 seconds. GPU0 used 23,603 MiB after each chat admission; the 1060s stayed idle. Host `MemAvailable` after A/B was 15.39/15.14 GiB. NVMe block reads during A/B admission were approximately 105.2/100.7 GB. These device totals can include unrelated I/O, but the rig had no other benchmark load. The live Strata log reported changing expert-cache hit rates during the run. Large cold reads and unstable decode rates make this a useful capacity/isolation proof, not a single steady-state speed score. Physical KV residence was not established. No third chat or deeper occupied history was tested. The runner has a 4 GiB host-memory floor and a 26 GB host-drop guard.

The original runner stopped Strata at test completion before the operator asked to leave it loaded. A subsequent manual launch used the same model/pack, 32K context, two slots, INT8 KV and memory settings, with no test chat state restored. Future probes can use the runner's `--reuse-loaded` flag, which checks the matching resident model and leaves it loaded. Successful fresh runs now freeze by default; `--stop-after` explicitly stops them. Failed fresh runs clean up. The durable [terminal receipt](q4_two_chat_detail/terminal.json) and response JSON files hold timings, memory and I/O snapshots, exact answers and engine metadata.
