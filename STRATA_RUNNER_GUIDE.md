# Strata experiment runner guide

This is the benchmarking repo's intake and execution contract for Strata tests. Use [TEST_RUNNER_GUIDE.md](TEST_RUNNER_GUIDE.md) for the common experiment lifecycle and compiler. [STRATA_MEMORY_TEST_PLAN.md](STRATA_MEMORY_TEST_PLAN.md) and [EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md) retain dated findings, raw receipts, and open research questions. A new model, card, budget, context, or prompt is a new **case**, not a new launcher.

## Start with the question

| Example request | Case family and endpoint | Main missing choice when the request is loose |
|---|---|---|
| “Can this model run in Strata on the 3090?” | `model_fit`: catalog compatibility, read-only plan, guarded load, answer, actual placement | Exact supported family/pack and artifact; requested context |
| “Try a 70B with mostly RAM and the 3090” | Compatibility gate first; then fit only if a supported pack exists | Which exact model/quant? Does RAM mean experts/weights or KV? Is 3090 the only GPU? Do not silently switch engine or model. |
| “How little RAM can Q4 use?” | Resident-budget sweep: successful fit, latency, physical storage reads, host headroom | Allowed budget range, context and workload; distinguish fastest from minimum viable |
| “Does 16 GiB beat 12 GiB?” | Paired budget replay under independent loads, alternating order | Speed, I/O, or chat quality endpoint; cold/warm policy |
| “3090 versus 3090 plus 1060?” | Placement comparison: one GPU, layer split, or native helper cache | Which placement mechanism? A helper cache is decode-only and is not a layer split or expert row sharding. |
| “Do the 1060s help?” | Separate layer-split and helper-cache cases; report prefill and decode separately | CUDA backend and selected physical helpers; reserve/headroom |
| “Can it handle two long chats?” | `chat_sequence`: per-slot fit, state isolation, continuation, aggregate latency | Slot count, context cap per slot, occupied depth, concurrent or sequential requests |
| “How fast at 50K or 256K?” | `depth_replay`: actual occupied tokens, first token, prefill, decode, recall | A 256K *cap* with 50K occupied text is a 50K test, not 256K recall |
| “NVMe versus SATA?” | Storage-tier comparison: same pack bytes and memory settings, cold and warm phases | Which file moves, and whether cache eviction is allowed on an idle rig |
| “Does MTP/DFlash2 help?” | Drafting A/B with matched prompt, output cap and correctness | Exact mode/build; acceptance rate and generated-token count must be recorded |
| “Q2 versus Q4?” | Cross-quant fit, quality, and speed study | Model family, separate quality fixture, context/KV and capacity policy; bytes differ, so this is not a same-file engine A/B |
| “Strata versus llama.cpp?” | Engine A/B on identical GGUF bytes when supported | Same artifact, card, context, KV, cache, prompt, output and repeat policy |
| “Put the PLE table or experts on helpers” | `component_probe` first; later full-model experiment if the bridge passes correctness | Native Strata helper cache, whole-expert placement, and PLE row sharding are different mechanisms |
| “Should we update Strata?” | Version regression: plan, load, correctness, placement, speed on same pack | Old/new control and engine builds; keep the installed baseline pinned |

For a request that merely says “test,” default to a guarded fit and short correctness smoke, and label it as such. Ask a compact clarification only when model compatibility, residency target, or claimed endpoint cannot be inferred from the library and existing cases. If the user requests a speed or quality claim, establish its control and fixture before launch.

## Resolved case fields

Every case records `question`, `endpoint`, `result_class`, `baseline`, `model_id`, `family`, `pack`, exact GGUF/pack hashes, control/engine build and CUDA backend, `load_path`, physical GPU UUIDs and roles, `placement_mode`, context cap, actual occupied tokens, KV type/location, slot count, resident expert budget, GPU expert cache, file tier/device, MTP/draft mode, prompt/state fixture hash, output cap, warmup, repetitions, cache policy, memory limits, and stop/cleanup rule. Mark `not_applicable` explicitly. Record both requested and *observed* residency, GPU memory, `MemAvailable`, process memory, page cache, swap, physical block reads, load time, first-token/prefill/decode/full-request times, generated tokens, correctness oracle, and unavailable telemetry.

`placement_mode` is one of `single_gpu`, `layer_split`, `native_helper_cache`, or `experimental_bridge`. It is independent of `storage_tier` and `resident_expert_budget_gib`. The bridge mode needs a named adapter and proof class. Pipeline windows are another option, only when supported by the installed build and valid for the selected card topology. Resolve card roles to UUID/PCI bus at run time and save the mapping. A CLI plan is an admission input, not proof that a load fits or that requested placement happened.

## Load path and phases

Two registered Strata packs already have managed gateway recipes: Qwen3.6 XL and Qwen3.8 Q2. The gateway Manager handles fit/admission and the orchestration rig runtime owns their pinned launch, readiness, host-memory guard, stop, and lease. Current managed recipes validate GPU0 alone and reject arbitrary Strata runtime options. Use this route for cases it can express. A Q4 budget, alternate engine build, helper cache, or experimental placement currently needs a benchmarking-owned direct adapter under a Manager run/claim. Promote a stable mode into a registered recipe rather than carrying a second permanent launcher. Neither path downloads a model during a benchmark.

The adapter phases are: resolve request and catalog support; scan hardware/claims; verify exact artifacts and build; run non-allocating `strata launch --plan`; obtain Manager admission/claim; launch; verify route, health and effective placement; warm up; run fixed requests and telemetry; check the oracle; stop and release; write checkpoint and terminal receipt even on refusal or failure. Stop on memory pressure, swap activity beyond the case guard, wrong GPU mapping, mismatched hash, or missing physical-I/O instrumentation when I/O is the endpoint. Do not clear global page cache while another service is active.

For a **new** request, use the schema-3 compiler for parameter and order expansion, then `run_model_loading_sequence.py` for the ordered session when its adapter supports the case. Historical one-off scripts are examples of questions and controls, not a migration backlog. Read their receipts to learn what worked, then make a fresh case and reusable adapter only for the newly requested test. Do not re-run or convert past cases to justify retiring their scripts. Preserve workload fixtures and result classes where they remain useful. The current compiler does not yet implement Strata catalog resolution or verify actual placement; a compiled case is not executable until its adapter and no-load preview pass.

## Comparison rules and current evidence

- Change one primary variable per pair. For card, budget, KV, or engine comparisons, use A/B/A or alternating order and multiple prompts. Pin the same model bytes, context, occupied depth, fixture, output cap, draft mode and cache policy wherever the variable permits. Report load, prefill, decode, complete request, host/VRAM headroom and physical I/O as a tradeoff, not a single score.
- A long context **reservation** and long **occupied chat** are separate axes. A visible-answer/recall check is separate from a timing request whose tokens remain in the reasoning field. Component lookup accuracy or one-expert speed is not full-model inference evidence.
- Nov 6 Q2 layer splitting reduced NVMe reads but slowed the short-context 3090-only baseline. Nov 10 Q4 native 1060 expert caching held 5.21 GiB but did not improve one matched 16/32/50K series. These outcomes justify testing each mechanism with its own endpoint, not assuming extra cards help.
- Nov 14 Q4 12/16 GiB resident-budget runs add two useful templates. At fixed ~50K input, 16 GiB shortened one full request by 6.9% and reduced NVMe block reads by 27.15 GB, leaving less free host RAM. In the two-chat five-request sequence, totals were 494.50 s and 490.12 s; the larger budget did not materially shorten that sequence. Both were one load per arm in 16→12 order, so repeat in alternating order before a general speed claim. See `results/runtime_experiments/q38_fixed50k_speed_20261114/README.md` and `results/runtime_experiments/q38_q4_twochat_budget_20261114/README.md`.

## Upstream and installed-build delta (checked 2026-11-15)

The rig recipe pins Strata control 0.2.10 and engine 0.1.56. [Upstream releases](https://github.com/Niko1221/Strata/releases) list 0.2.13 with control/engine 0.1.59. The newer release changes DFlash2 defaults by card and fixes Linux expert-store loading when memory conditions permit; these can change the effective baseline. [Multi-GPU documentation](https://github.com/Niko1221/Strata/blob/main/docs/MULTI_GPU.md) describes Main/Helper/Off roles, layer splits, native helper caches and pipeline windows; read the installed `strata launch --help` before assuming a documented switch exists in 0.2.10. [The model catalog](https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md) is a compatibility input, not a reason to substitute a different pack. Run a separate old/new version regression before updating a recipe or comparing speed across builds.

Q4 PLE row sharding remains a separate patched llama.cpp bridge experiment; successful exact-row reads do not make it a Strata feature. The current Q4 pack reads experts from GGUF shards and has no `experts.bin`; verify the pack format before any budget or storage case. The rig's CUDA13 engine does not run GTX 1060 kernels directly; native 1060 helper tests have used CUDA12. Preserve these build and pack distinctions in case IDs and receipts.
