#!/usr/bin/env python3
"""Run the frozen understanding suite against a local Step3-VL checkpoint."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from run_vision_understanding import normalize, parse_answer


KEY_MAPPING = {
    "^vision_model": "model.vision_model",
    r"^model(?!\.(language_model|vision_model))": "model.language_model",
    "vit_large_projector": "model.vit_large_projector",
}


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--gpu-max-gib", type=int)
    parser.add_argument("--cpu-max-gib", type=int)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.max_tokens < 1 or (args.gpu_max_gib is not None and args.gpu_max_gib < 1) or (args.cpu_max_gib is not None and args.cpu_max_gib < 1) or (args.limit is not None and args.limit < 1):
        parser.error("token, memory, and case limits must be positive")
    if not args.model_dir.is_dir() or args.output.exists():
        parser.error("model directory must exist and output directory must be new")
    cases = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        cases = cases[:args.limit]
    for case in cases:
        if not (args.manifest.parent / case["image"]).is_file():
            parser.error(f"missing image for {case['id']}")
    args.output.mkdir(parents=True)
    context_file = args.output / "run_context.json"
    context = {"started_at": stamp(), "status": "loading", "pid": os.getpid(), "backend": "transformers",
               "model_dir": str(args.model_dir.resolve()),
               "manifest": str(args.manifest.resolve()),
               "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
               "planned_cases": len(cases), "max_tokens": args.max_tokens,
               "requested_gpu_max_gib": args.gpu_max_gib,
               "requested_cpu_max_gib": args.cpu_max_gib, "temperature": 0}
    context_file.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        import torch
        from transformers import AutoProcessor, AutoModelForCausalLM
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU unavailable")
        visible_gpu = torch.cuda.current_device()
        gpu_max_gib = args.gpu_max_gib or max(1, torch.cuda.get_device_properties(visible_gpu).total_memory // (1024**3) - 3)
        mem_available_kib = next(int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
        cpu_max_gib = args.cpu_max_gib or max(1, mem_available_kib // (1024**2) - 4)
        started = time.monotonic()
        processor = AutoProcessor.from_pretrained(str(args.model_dir), trust_remote_code=True,
                                                   local_files_only=True)
        model = AutoModelForCausalLM.from_pretrained(
            str(args.model_dir), trust_remote_code=True, local_files_only=True,
            device_map="auto", torch_dtype="auto", key_mapping=KEY_MAPPING,
            max_memory={visible_gpu: f"{gpu_max_gib}GiB", "cpu": f"{cpu_max_gib}GiB"},
        ).eval()
        context.update(status="running", load_seconds=round(time.monotonic()-started, 3),
                       gpu_max_gib=gpu_max_gib, cpu_max_gib=cpu_max_gib,
                       torch_version=torch.__version__,
                       transformers_version=__import__("transformers").__version__,
                       gpu_name=torch.cuda.get_device_name())
        context_file.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        context.update(status="failed", finished_at=stamp(), error=f"{type(exc).__name__}: {exc}")
        context_file.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        raise

    results = []
    with (args.output / "results.jsonl").open("x", encoding="utf-8") as receipt:
        for index, case in enumerate(cases, 1):
            started = time.monotonic()
            image_path = args.manifest.parent / case["image"]
            instruction = (
                'Return only JSON with this schema: {"answer":"short answer",'
                '"evidence":["visible evidence"],"visible_text":[],"confidence":0.0}. '
                + case["prompt"]
            )
            try:
                messages = [{"role": "user", "content": [
                    {"type": "image", "url": str(image_path)},
                    {"type": "text", "text": instruction},
                ]}]
                inputs = processor.apply_chat_template(
                    messages, add_generation_prompt=True, tokenize=True,
                    return_dict=True, return_tensors="pt",
                ).to(model.device)
                torch.cuda.reset_peak_memory_stats()
                with torch.inference_mode():
                    ids = model.generate(**inputs, max_new_tokens=args.max_tokens, do_sample=False)
                raw = processor.decode(ids[0, inputs["input_ids"].shape[-1]:],
                                       skip_special_tokens=True)
                answer, schema_ok = parse_answer(raw)
                correct = normalize(answer) in {normalize(v) for v in case["expected"]["answers"]}
                error = None
            except Exception as exc:
                raw = answer = ""
                schema_ok = correct = False
                error = f"{type(exc).__name__}: {exc}"
            row = {"id": case["id"], "category": case["category"], "answer": answer,
                   "expected": case["expected"]["answers"], "correct": correct,
                   "schema_ok": schema_ok, "seconds": round(time.monotonic()-started, 3),
                   "peak_cuda_allocated_mib": round(torch.cuda.max_memory_allocated()/1048576),
                   "raw": raw, "error": error}
            results.append(row)
            receipt.write(json.dumps(row) + "\n")
            receipt.flush()
            os.fsync(receipt.fileno())
            print(f"[{index}/{len(cases)}] {case['id']}: correct={correct} schema={schema_ok}"
                  f"{' error='+error if error else ''}", flush=True)
            if len(results) >= 3 and all(item["error"] for item in results[-3:]):
                break
    categories = {}
    for category in sorted({item["category"] for item in results}):
        group = [item for item in results if item["category"] == category]
        categories[category] = {"correct": sum(item["correct"] for item in group),
                                "total": len(group)}
    summary = {"suite": "local-understanding-full-v1" if args.manifest.parent.name == "local-full-v1" else "local-understanding-v1",
               "model": str(args.model_dir), "cases": len(results),
               "correct": sum(item["correct"] for item in results),
               "schema_rate": sum(item["schema_ok"] for item in results)/len(results) if results else 0,
               "categories": categories, "cloud_dependencies": False}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    context.update(status="complete" if len(results) == len(cases) else "failed",
                   completed_cases=len(results), finished_at=stamp())
    if context["status"] == "failed":
        context["error"] = "three consecutive case errors"
    context_file.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if context["status"] == "failed":
        raise SystemExit(context["error"])


if __name__ == "__main__":
    main()
