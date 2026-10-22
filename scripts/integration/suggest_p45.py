#!/usr/bin/env python3
"""Suggest Phase 4.5 experiments from a model's own Phase 4 results (NEW_MODEL_INTEGRATION.md, Phase 4.5).

usage: suggest_p45.py MODEL RUN_NAME [--litmus FILE] [--thinking-template yes|no] [--records FILE] [--history DIR]

Phase 4.5 is an optional menu: a model tries only the options that bear on what its Phase 4 showed. This
reads that evidence and prints one line per suggested experiment, with the evidence behind it:
  - the unreadable counts of the run's flexible reasoning rows (extract v5 and later),
  - what the answers of a task with many unreadable ones look like (empty, opening with JSON or a code
    fence, thinking tags, very long), from the run's logged samples,
  - the model's registry profile (a system prompt about output formats, thinking on by default),
  - the Phase 3 litmus checks that failed (the lane's litmus output file).
It suggests only; nothing is run. The lane itself runs the thinking on/off A/B when the template has a
thinking control. Prints `NOTHING TO FIX` when Phase 4 showed no problem these checks can see.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BENCH = HERE.parents[1]
HISTORY = Path("/mnt/shared/logs/benchmarks/bench-reasoning/history")

FLEXIBLE = {"bbh_flexible": "bbh", "drop_flexible": "drop", "mmlu_pro_flexible": "mmlu_pro",
            "gsm8k_flexible": "gsm8k"}
UNREADABLE_SHARE = 0.2    # a task with at least this share of unreadable answers is a problem
SHAPE_SHARE = 0.5         # an answer shape covering this share of a task's answers names the cause
LONG_CHARS = 1500
FORMAT_WORDS = re.compile(r"(?i)\bjson\b|markdown|code block|```")
EXTRACT_VERSION = re.compile(r"extract-v(\d+)$")


def load_extractor():
    spec = importlib.util.spec_from_file_location("extract_reasoning_results",
                                                  BENCH / "scripts" / "active" / "extract_reasoning_results.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_rows(records: Path, model: str, run: str) -> dict[str, dict[str, Any]]:
    """The newest successful row per test of one run, flexible rows only from extract v5 on (before v5
    their failure count was the rescued count, not the unreadable one)."""
    rows: dict[str, dict[str, Any]] = {}
    for line in records.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("model") != model or r.get("suite") != run or r.get("status") != "success":
            continue
        if r.get("test_id") in FLEXIBLE:
            version = EXTRACT_VERSION.search(str((r.get("runtime") or {}).get("config_id") or ""))
            if not version or int(version.group(1)) < 5:
                continue
        if r["test_id"] not in rows or str(r.get("run_at")) >= str(rows[r["test_id"]].get("run_at")):
            rows[r["test_id"]] = r
    return rows


def task_answers(history: Path, model: str, run: str, task: str, extractor) -> list[str]:
    """The run's raw answers for one task (newest result set; gsm8k logs one sample per filter)."""
    files = sorted((history / f"bench-reasoning_{model.replace(':', '_')}_{run}" / task).glob("**/results_*.json"))
    if not files:
        return []
    stamp = files[-1].stem.removeprefix("results_")
    by_doc: dict[Any, str] = {}
    for f in sorted(files[-1].parent.glob(f"samples_*_{stamp}.jsonl")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
            if line.strip():
                s = json.loads(line)
                by_doc.setdefault((f.name, s.get("doc_id", i)) if task != "gsm8k" else s.get("doc_id", i),
                                  extractor._response(s))
    return list(by_doc.values())


def shapes(answers: list[str]) -> dict[str, int]:
    out = {"empty": 0, "format": 0, "think": 0, "long": 0}
    for a in answers:
        t = a.strip()
        out["empty"] += not t
        out["format"] += t.startswith("{") or t.startswith("```")
        out["think"] += "<think>" in a or "</think>" in a
        out["long"] += len(a) > LONG_CHARS
    return out


def litmus_failures(path: Path | None) -> list[tuple[str, str]]:
    if not path or not path.is_file():
        return []
    fails = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(\w+)\s+FAIL\s+content=(.*)", line)
        if m:
            fails.append((m.group(1), m.group(2)))
    return fails


def suggest(model: str, run: str, rows: dict, answers: dict[str, list[str]], profile: dict,
            litmus: list[tuple[str, str]], thinking_template: bool = False) -> list[str]:
    out: list[str] = []
    system_prompt = str(profile.get("system_prompt") or "")
    extra = [str(a) for a in profile.get("extra_args") or []]
    thinking_on = any(a == "--reasoning" and i + 1 < len(extra) and extra[i + 1] == "on" for i, a in enumerate(extra))
    prompt_about_formats = bool(FORMAT_WORDS.search(system_prompt))

    for test_id, task in FLEXIBLE.items():
        row = rows.get(test_id)
        if not row:
            continue
        n, unread = int(row.get("sample_count") or 0), int(row.get("extractor_failure_count") or 0)
        if not n or unread / n < UNREADABLE_SHARE:
            continue
        evidence = f"{task} answers unreadable {unread} of {n}"
        found = answers.get(task) or []
        shape = shapes(found)
        total = max(1, len(found))
        named = False
        if shape["format"] / total >= SHAPE_SHARE:
            note = " (the profile's system prompt is about output formats)" if prompt_about_formats else ""
            out.append(f"SUGGEST system-prompt: {evidence}; {shape['format']} of {len(found)} open with JSON "
                       f"or a code fence{note}. Try a system prompt without format rules, or none.")
            named = True
        if shape["think"] / total >= SHAPE_SHARE:
            out.append(f"SUGGEST template-or-thinking: {evidence}; {shape['think']} of {len(found)} contain "
                       f"thinking tags. Try thinking off, or the template switch that hides the thinking.")
            named = True
        if shape["empty"] / total >= SHAPE_SHARE:
            if thinking_on:
                cause = "thinking is on in the profile, so the budget may be spent before the answer"
            elif thinking_template:
                cause = "the chat template can think, and may think by default without a flag"
            else:
                cause = "the task's stop sequence may fire on the model's first line"
            out.append(f"SUGGEST thinking-or-budget: {evidence}; {shape['empty']} of {len(found)} are empty "
                       f"({cause}). Try thinking off, a reasoning budget, or a larger output budget.")
            named = True
        if shape["long"] / total >= SHAPE_SHARE:
            out.append(f"SUGGEST output-budget: {evidence}; {shape['long']} of {len(found)} run past "
                       f"{LONG_CHARS} characters. Try a larger output budget, or thinking off.")
            named = True
        if not named:
            out.append(f"SUGGEST system-prompt, output-budget or thinking-off: {evidence}; no single answer "
                       f"shape explains it ({len(found)} answers read). Read the samples, then pick one.")

    for check, content in litmus:
        if "```" in content:
            out.append(f"SUGGEST system-prompt: litmus {check} failed with a fenced answer ({content[:60]}). "
                       f"Try a system prompt that asks for raw output, if a suite needs it raw.")
        elif "<think>" in content or "</think>" in content:
            out.append(f"SUGGEST template-or-thinking: litmus {check} failed with thinking tags in the answer. "
                       f"Try thinking off or a template switch.")
        else:
            out.append(f"SUGGEST read-the-answer: litmus {check} failed ({content[:60]}).")

    if thinking_on:
        out.append("NOTE thinking is on by default in the registry profile; the lane's thinking A/B measures "
                   "off against on (time per run matters as much as the score).")
    if not [line for line in out if line.startswith("SUGGEST")]:
        out.insert(0, f"NOTHING TO FIX: Phase 4 of {run} shows no unreadable task and no failed litmus check; "
                      f"Phase 4.5 is optional for {model}.")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("model")
    ap.add_argument("run")
    ap.add_argument("--litmus", type=Path)
    ap.add_argument("--thinking-template", choices=("yes", "no"), default="no",
                    help="whether the model's chat template has a thinking control (the lane checks /props)")
    ap.add_argument("--records", type=Path, default=BENCH / "results" / "model_benchmark_records.jsonl")
    ap.add_argument("--history", type=Path, default=HISTORY)
    ap.add_argument("--registry", type=Path, default=BENCH / "model_registry.json")
    a = ap.parse_args()
    extractor = load_extractor()
    rows = run_rows(a.records, a.model, a.run)
    if not rows:
        print(f"NO RESULTS: no recorded rows for {a.model} run {a.run}; nothing to suggest from.")
        return 0
    answers = {task: task_answers(a.history, a.model, a.run, task, extractor) for task in FLEXIBLE.values()}
    registry = json.loads(a.registry.read_text(encoding="utf-8"))["models"]
    profile = ((registry.get(a.model) or {}).get("profiles") or {}).get("default") or {}
    for line in suggest(a.model, a.run, rows, answers, profile, litmus_failures(a.litmus),
                        a.thinking_template == "yes"):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
