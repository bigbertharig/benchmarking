# Benchmark execution plan

## Hardware tiers

Keep measured results tied to the hardware actually installed. Run the rig
inventory scan before placement and record the card IDs and free VRAM in each
receipt. The table below describes capacity tiers, not a fixed card count:

| Tier | Placement | Nominal VRAM | Priority |
| --- | --- | ---: | --- |
| Side A | one available side card | measured | preferred always-resident image tool |
| Side B | two available side cards | measured | larger specialist fallback |
| Side C | three available side cards | measured | lowest-priority side deployment |
| Side pool | available side cards | measured | specialist experiment |
| Full rig | all available cards | measured | maximum-size experiment only |

These are capacity labels, not safe model-file limits. Projectors, KV cache,
compute buffers, image resolution, and allocator headroom all count against
VRAM. Report whether the complete runtime fits reliably in its assigned tier;
interconnect and speed characterization are out of scope for model selection.

## 1. Endpoint integration smoke

1. Load one vision model through the rig controller without displacing active
   chat services.
2. Verify a single image request through the OpenAI-compatible endpoint.
3. Run `local-v1/smoke.jsonl`: one local case each for OCR, documents,
   charts, GUI reading, abstention, and spatial/counting.
4. Record parser failures, unsupported image forms, peak VRAM, cold-load time,
   and per-sample latency.

The prepared runner is `scripts/active/run_vision_understanding.py`. It accepts only a
loopback endpoint and reads all PNGs and answers from this repository.

This stage validates the pipeline only; its limited scores are not official.

After the smoke succeeds, run all 24 frozen local-v1 cases, then the 120-case
`local-full-v1` suite. These are local synthetic screening scores, not official
scores for the public benchmarks that inspired their coverage.

## 2. Candidate comparison

Run the complete frozen local suite with identical prompts, decoding settings,
images, checksums, and scoring for every checkpoint. Add a new suite version
when expanding coverage; never change a suite during a model comparison.

## 3. Selection gates

A candidate must:

- fit the intended one-, two-, or three-card tier with safe VRAM margin;
- complete the offline battery without systematic transport/parser failures;
- avoid catastrophic weakness in OCR, charts, GUI screenshots, or abstention;
- return concise structured evidence suitable for a downstream tool call;
- fit reliably in its assigned 8, 16, or 24 GB deployment tier.

## 4. Generation track

Before testing generation candidates, freeze local prompts, reference images,
and deterministic scorers. Hosted judges and runtime downloads are excluded;
human blind review may supplement local automatic metrics.
