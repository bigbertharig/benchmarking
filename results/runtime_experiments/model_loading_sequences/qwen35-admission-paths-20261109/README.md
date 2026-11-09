# Qwen35 F16 chat-admission placement, 100K → 150K (2026-11-09)

All arms used the same Qwen3.6-35B-A3B Q4_K_XL weights on GPU0 and saved
100K F16 chat states. The destination chats used F16 KV with 262,144
reserved positions. New history brought each chat to 150,000 occupied
tokens; private-code recall passed. Model load, saved-state restore,
incremental fill, handoff, and recall were measured separately.

| Placement | Resident chat capacity | Measured incremental admission |
| --- | ---: | ---: |
| Direct fill on one 1060 (ubatch 32) | 5 cards available | 749.2 s for one chat; 775.8 s including source restore |
| Five direct 1060 fills together (ubatch 32) | 5 chats | 866.4 s until all five ready; 976.4 s including five source restores |
| GPU0+GPU1 temporary F16 KV, restore on GPU2 | 4 chats; GPU1 dedicated prep | 409.4 s fill + 13.1 s handoff for one chat |
| GPU0 weights, temporary KV in RAM | 5 chats | 593.2–593.9 s to usable for each sequential chat (four measured) |

The first direct chat became ready 846.9 seconds after the five-way fill
started; all five were ready at 866.4 seconds. Restoring five saved source
states took 110.0 seconds before fill. The split arm measured
only one chat; four sequential admissions are an inference, not a measured
four-chat result. The RAM arm was canceled after four admissions, before
150K generation; its setup/timing scope differs slightly from the split
arm, so use the detailed receipt before comparing seconds exactly.

Five simultaneous direct fills took only about 16% longer than one solo
fill, so direct worker preparation can overlap despite sharing GPU0 model
computation. The dedicated helper is faster for admitting one chat but
reserves a 1060, leaving four worker slots. We have not measured four
sequential helper admissions or the delay imposed on already generating
workers. A five-chat direct fill therefore establishes higher batch
throughput here, while the helper establishes faster first admission.

These times compare complete preparation paths, not PCIe x1 and RAM raw
bandwidth. Direct workers reserved 262,144 F16 positions with batch 64;
the helper prepared in a 155,648-position temporary context with batch 512.
The RAM and dedicated GPU1 preparation paths had similar temporary caps,
and the dedicated helper was about 29% faster than the roughly 594-second
RAM preparation in this run. Model cold load and sustained 150K answer
generation were not measured. No 200K extension was run in this round.

The separate 100K → 108K pilot tested direct worker ubatch 8 and 32.
Ubatch 32 reduced solo fill from 111.3 to 105.6 seconds and five-way fill
from 128.9 to 121.6 seconds;
therefore the full direct 150K arms used ubatch 32.

The transient split variant prepared with GPU0+GPU1 then placed the chat
on GPU1. It passed in 422.7 seconds after source restore, but it does not reserve a separate helper
card. The modular variant kept GPU1 as a dedicated helper and restored
the finished chat on GPU2 in 422.5 seconds. Its
maximal simultaneous worker layout uses GPUs2–5, leaving four chat slots.
Direct filling uses GPUs1–5 for five slots. No arm gives a 1060 a full
independent model: all still share GPU0 weights and computation.

The pilot's first attempt failed a 512-versus-64 token batch assertion
before filling any new history. The isolated direct build corrected the
helper's chunk size to 64, and the retry passed. Logs and GPU samples are
under `/mnt/shared/experiments/kv-matrix-20261107/` with the labels in
the linked campaigns. Model cold-load times are excluded from the table.

Evidence: [receipt](receipt.json),
[direct 108K pilot](../../../../campaigns/qwen35_f16_direct_admission_108k_pilot_20261109.json),
[ubatch 32 pilot](../../../../campaigns/qwen35_f16_direct_admission_108k_ub32_pilot_20261109.json),
[direct 150K campaign](../../../../campaigns/qwen35_f16_direct_admission_150k_20261109.json),
[modular split campaign](../../../../campaigns/qwen35_f16_dedicated_prep_150k_20261109.json),
[transient split campaign](../../../../campaigns/qwen35_f16_split_admission_150k_20261109.json),
[direct patch](direct.patch), [modular split patch](dedicated.patch), and
[build recipe](build.sh). Terminal receipts are adjacent under the run IDs
listed in the campaigns.
