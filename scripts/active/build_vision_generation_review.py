#!/usr/bin/env python3
"""Build a portable offline review gallery and score sheet for a generation run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import shutil


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("review output must be a new directory")
    context = json.loads((args.run / "run_context.json").read_text(encoding="utf-8"))
    manifest_bytes = args.manifest.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != context["manifest_sha256"]:
        parser.error("manifest hash differs from benchmark run")
    cases = {case["id"]: case for case in map(json.loads, manifest_bytes.splitlines())}
    rows = [json.loads(line) for line in (args.run / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    if not rows:
        parser.error("run contains no result rows")
    args.output.mkdir(parents=True)
    (args.output / "images").mkdir()
    (args.output / "sources").mkdir()
    gallery = []
    sheet = []
    for row in rows:
        case = cases[row["id"]]
        image_name = f"{row['id']}-seed{row['seed']}.png"
        image_relative = ""
        if row["image"]:
            image_path = args.run / row["image"]
            if hashlib.sha256(image_path.read_bytes()).hexdigest() != row["image_sha256"]:
                raise ValueError(f"output image hash differs: {image_path}")
            shutil.copy2(image_path, args.output / "images" / image_name)
            image_relative = f"images/{image_name}"
        source_relative = ""
        if case.get("source_image"):
            source_path = args.manifest.parent / case["source_image"]
            source_name = Path(case["source_image"]).name
            dest = args.output / "sources" / source_name
            if not dest.exists():
                shutil.copy2(source_path, dest)
            source_relative = f"sources/{source_name}"
        checklist = " · ".join(case["requirements"])
        sheet.append({
            "case_id": row["id"], "seed": row["seed"], "category": case["category"],
            "prompt": case["prompt"], "requirements": checklist,
            "source": source_relative, "output": image_relative,
            "error": row["error"] or "", "requirements_met_0_to_3": "",
            "visual_quality_0_to_3": "", "edit_preservation_0_to_3": "",
            "notes": "",
        })
        preview = f'<img src="{html.escape(image_relative)}" alt="generated output">' if image_relative else '<p>Generation failed.</p>'
        source = f'<img src="{html.escape(source_relative)}" alt="edit source">' if source_relative else ""
        gallery.append(
            '<article><h2>' + html.escape(f"{row['id']} · seed {row['seed']}") + '</h2>'
            '<p><b>Prompt:</b> ' + html.escape(case["prompt"]) + '</p>'
            '<p><b>Check:</b> ' + html.escape(checklist) + '</p>'
            '<div class="pair">' + source + preview + '</div>'
            + ("<p>" + html.escape(row["error"]) + "</p>" if row["error"] else "")
            + '</article>'
        )
    with (args.output / "review.csv").open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(sheet[0]))
        writer.writeheader()
        writer.writerows(sheet)
    page = ('<!doctype html><meta charset="utf-8"><title>Vision generation review</title>'
            '<style>body{font:16px system-ui;background:#182230;color:#f2f5f9;margin:2rem}'
            'article{background:#263446;padding:1rem;margin:1rem 0;border-radius:.5rem}'
            '.pair{display:flex;gap:1rem;flex-wrap:wrap}.pair img{max-width:45%;max-height:540px;object-fit:contain}'
            '</style><h1>Vision generation review</h1>'
            '<p>Review each output against its prompt and checklist. Enter scores in review.csv. '
            'The gallery is for inspection; no automatic visual-quality score is inferred.</p>'
            + ''.join(gallery))
    (args.output / "index.html").write_text(page, encoding="utf-8")
    print(f"Review gallery: {args.output / 'index.html'}")
    print(f"Score sheet: {args.output / 'review.csv'} ({len(sheet)} rows)")


if __name__ == "__main__":
    main()
