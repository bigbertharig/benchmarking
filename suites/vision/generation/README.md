# Image-generation and editing benchmarks

Generation and editing are recorded as separate tracks even when one checkpoint supports both.

The downloaded Qwen3.5, Gemma 4, and Step3-VL vision checkpoints accept images
and produce text; they are not image-generation candidates. This track needs
separate text-to-image and instruction-editing models.

`local-full-v1/cases.jsonl` is the frozen local input bank: 36 text-to-image
prompts and 12 editing instructions, each with four fixed seeds. The editing
cases include 12 synthetic source PNGs. `SHA256SUMS` covers the manifest and
source images. The generator refuses to overwrite an existing suite. Full
runtime baselines for SDXL and Instruct Pix2Pix are recorded in
[`results/vision`](../../../results/vision); image-quality scoring is pending.
`scripts/active/run_vision_generation.py` accepts a local Diffusers checkpoint,
refuses network model fetches, and writes each output and receipt as it finishes.
Keep the compact receipts under `results/vision` and the generated images in a
referenced artifact archive.
Image quality still requires blind review against the requirements checklist;
the runner records performance and failures, not a fabricated quality score.

The completed 2026-11-20 output archives, raw GPU telemetry, and review
galleries are under `benchmark-results/vision/2026-11-20/` on the shared drive
(`sdxl-full144` and `pix2pix-full48`). The Pix2Pix safety checker replaced
three generated edits with black images; the case-level receipts and gallery
mark them as blocked. Review the 144 SDXL and 48 Pix2Pix outputs in their
separate track galleries before drawing image-quality conclusions.

The first local baselines are SDXL base 1.0 for `text_to_image` and Instruct
Pix2Pix for `image_editing`. The shared model archive pins their downloaded
revisions in `generation-baseline-download-20261120.json`. They test two
different capabilities; compare models within a track when additional
checkpoints are added. A full local run contains 144 text-to-image outputs or
48 editing outputs. Verify the source manifest against `SHA256SUMS` before
running either track.

After a run, `scripts/active/build_vision_generation_review.py --manifest
suites/vision/generation/local-full-v1/cases.jsonl --run RESULTS_DIRECTORY
--output NEW_REVIEW_DIRECTORY` creates a portable gallery and blank CSV score
sheet. Score each output 0–3 for prompt requirements and visual quality:
0 = failed or absent, 1 = major errors, 2 = mostly met with minor errors,
3 = fully met. For editing, also score preservation of unrequested content on
the same scale; leave that column blank for text-to-image. The CSV keeps
the prompt, checklist, seed, source, output, and notes together. Treat these
scores as reviewer judgments, not automatic measurements.

## Public benchmark battery

Use GenEditEvalKit's official task implementations where available:

| Track | Benchmark | Primary purpose |
| --- | --- | --- |
| Text-to-image | GenEval | Compositional prompt adherence |
| Text-to-image | DPG-Bench | Dense prompt following |
| Text-to-image | Qwen-Image-Bench | Creator-oriented quality and usefulness |
| Editing | GEdit | Instruction-based editing |
| Editing | ImgEdit | Editing quality and preservation |

Preserve each benchmark's native metric. Automated VLM-judge scores are useful
diagnostics but must not be the only ranking signal.

## Local deployment holdout

### Text-to-image: 36 prompts

| Category | Prompts |
| --- | ---: |
| Objects, attributes, and prompt adherence | 8 |
| Spatial composition and counting | 6 |
| Typography and signage | 6 |
| People, hands, and interactions | 4 |
| Photorealism and materials | 4 |
| Illustration and style control | 4 |
| Difficult negatives and exclusions | 4 |

### Editing: 12 cases

- four local object/attribute edits;
- two text replacements;
- two background or lighting changes;
- two additions/removals requiring preservation elsewhere;
- two multi-reference or identity-consistency cases.

Generate four fixed seeds per prompt in the full run. The smoke run uses 12 representative prompts and two fixed seeds.

## Holdout scoring

Use blind human pairwise preference as the primary quality measurement. Preserve source images, prompts, seeds, and anonymous output IDs.

Secondary measurements:

- prompt requirements satisfied as an explicit checklist;
- OCR accuracy for rendered text;
- object count and spatial-relation accuracy;
- edit success and preservation outside the edited region;
- diversity across seeds;
- failure rate, wall time, and peak memory.

Automated aesthetic or VLM-judge scores are diagnostic only. They must not be the sole ranking because they can favor a model family or visual style.
