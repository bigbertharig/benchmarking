# Image-understanding benchmarks

The target is a compact model that can provide reliable, concise image evidence
to another model. It is not primarily a chat-quality test.

## Active offline battery

`local-v1` contains 24 deterministic PNG cases, four in each category:

| Capability | Local category | Coverage inspiration |
| --- | --- | --- |
| OCR | `ocr` | OCRBench-style exact visible-text reading |
| Documents | `document` | DocVQA-style field and table extraction |
| Charts | `chart` | ChartQA-style values and arithmetic |
| GUI reading | `gui` | ScreenSpot-style interface state reading |
| Hallucination resistance | `negative` | POPE-style absence and abstention |
| Spatial/counting | `spatial` | MMStar-style basic perception/reasoning |

`smoke.jsonl` selects one case per category. `cases.jsonl` is the complete
first-pass suite. `SHA256SUMS` freezes the exact manifest and image bytes.

The builder and runner are `scripts/active/build_vision_understanding_suite.py` and
`scripts/active/run_vision_understanding.py`. The runner rejects non-loopback endpoints
and never imports a dataset client. Set `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` for every supervised run as an additional guard.

External benchmark names are coverage references only. Do not label local-v1
scores as MMStar, OCRBench, DocVQA, ChartQA, POPE, or ScreenSpot scores.

## Required outputs

Every prompt requests JSON with:

```json
{
  "answer": "short answer",
  "evidence": ["visible observation supporting the answer"],
  "visible_text": [],
  "confidence": 0.0
}
```

Schema compliance is scored separately from task accuracy. A correct answer hidden in invalid or excessively verbose output does not receive the schema point.

## Holdout reporting

Report category scores, exact-match accuracy, and schema compliance. Report the
complete runtime footprint and whether it fits the assigned 8/16/24 GB tier
separately; speed is not part of the selection score.

For calibration, confidence is evaluated with Brier score. Do not use the model's own prose as ground truth.

## Dataset policy

A runnable suite must be complete under this repository. Missing assets are a
hard failure and must never trigger a download. Keep answer keys out of model
prompts and record suite checksums with every comparison.
