#!/usr/bin/env python3
"""Run a frozen local image-generation or instruction-editing holdout."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--track", choices=("text_to_image", "image_editing"), required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--guidance-scale", type=float, default=7.5)
    parser.add_argument("--image-guidance-scale", type=float, default=1.5)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--limit", type=int, help="prompts, for smoke runs only")
    parser.add_argument("--seed-count", type=int, help="seeds per prompt, for smoke runs only")
    args = parser.parse_args()
    if args.steps < 1 or (args.limit is not None and args.limit < 1) or (args.seed_count is not None and args.seed_count < 1):
        parser.error("steps and optional limits must be positive")
    if not args.model_dir.is_dir():
        parser.error(f"local model is missing: {args.model_dir}")
    if args.output.exists():
        parser.error(f"refusing to overwrite existing output: {args.output}")
    cases = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = [case for case in cases if case["track"] == args.track]
    if args.limit is not None:
        cases = cases[:args.limit]
    if not cases:
        parser.error("no cases selected")
    for case in cases:
        if args.track == "image_editing" and not (args.manifest.parent / case["source_image"]).is_file():
            parser.error(f"missing edit source: {case['source_image']}")

    args.output.mkdir(parents=True)
    images = args.output / "images"
    images.mkdir()
    context = {
        "started_at": stamp(), "status": "loading", "track": args.track,
        "manifest": str(args.manifest),
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "model_dir": str(args.model_dir.resolve()),
        "steps": args.steps, "guidance_scale": args.guidance_scale,
        "image_guidance_scale": args.image_guidance_scale,
        "width_override": args.width, "height_override": args.height,
        "planned_prompts": len(cases),
        "planned_outputs": sum(len(c["seeds"][:args.seed_count]) for c in cases),
    }
    context_file = args.output / "run_context.json"
    context_file.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    try:
        import torch
        from PIL import Image
        from diffusers import AutoPipelineForText2Image, StableDiffusionInstructPix2PixPipeline

        if not torch.cuda.is_available():
            raise RuntimeError("a CUDA GPU is required for this local benchmark")
        pipeline_type = AutoPipelineForText2Image if args.track == "text_to_image" else StableDiffusionInstructPix2PixPipeline
        load_started = time.monotonic()
        pipe = pipeline_type.from_pretrained(
            str(args.model_dir), torch_dtype=torch.float16, variant="fp16",
            use_safetensors=True, local_files_only=True,
        ).to("cuda")
        context.update(status="running", load_seconds=round(time.monotonic()-load_started, 3),
                       torch_version=torch.__version__,
                       diffusers_version=__import__("diffusers").__version__,
                       gpu_name=torch.cuda.get_device_name())
        context_file.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        context.update(status="failed", finished_at=stamp(), error=f"{type(exc).__name__}: {exc}")
        context_file.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        raise
    receipt_path = args.output / "results.jsonl"
    complete = failed = consecutive_failures = 0
    with receipt_path.open("x", encoding="utf-8") as receipt:
        for case in cases:
            width = args.width or case["width"]
            height = args.height or case["height"]
            for seed in case["seeds"][:args.seed_count]:
                torch.cuda.reset_peak_memory_stats()
                start = time.monotonic()
                file = images / f"{case['id']}-seed{seed}.png"
                error = None
                try:
                    generator = torch.Generator(device="cuda").manual_seed(seed)
                    kwargs = {"prompt": case["prompt"], "generator": generator,
                              "num_inference_steps": args.steps,
                              "guidance_scale": args.guidance_scale,
                              "width": width, "height": height}
                    if args.track == "image_editing":
                        source = Image.open(args.manifest.parent / case["source_image"]).convert("RGB")
                        kwargs["image"] = source.resize((width, height))
                        kwargs["image_guidance_scale"] = args.image_guidance_scale
                    image = pipe(**kwargs).images[0]
                    temp = file.with_suffix(".tmp.png")
                    image.save(temp, format="PNG")
                    os.replace(temp, file)
                    complete += 1
                    consecutive_failures = 0
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    failed += 1
                    consecutive_failures += 1
                row = {"id": case["id"], "track": args.track, "category": case["category"],
                       "seed": seed, "image": str(file.relative_to(args.output)) if error is None else None,
                       "seconds": round(time.monotonic()-start, 3),
                       "peak_cuda_allocated_mib": round(torch.cuda.max_memory_allocated()/1048576),
                       "error": error}
                receipt.write(json.dumps(row) + "\n")
                receipt.flush()
                os.fsync(receipt.fileno())
                print(f"[{complete+failed}/{context['planned_outputs']}] {case['id']} seed={seed}"
                      f" {'FAILED: '+error if error else 'saved'}", flush=True)
                if consecutive_failures >= 3:
                    break
            if consecutive_failures >= 3:
                break
    context.update(status="failed" if consecutive_failures >= 3 else "complete",
                   finished_at=stamp(), completed_outputs=complete, failed_outputs=failed)
    if consecutive_failures >= 3:
        context["error"] = "stopped after three consecutive image-generation failures"
    context_file.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    if consecutive_failures >= 3:
        raise SystemExit(context["error"])


if __name__ == "__main__":
    main()
