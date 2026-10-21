#!/usr/bin/env python3
"""Re-score past bench-reasoning runs with the current extractor and record the flexible rows.

When extraction changes (extract v5, 2026-10-20: lenient MMLU-Pro, unreadable-answer counts),
the logged samples of past runs can be scored again without re-running the model. This walks
the suites already in model_benchmark_records.jsonl, finds each suite's history directory,
re-extracts its flexible rows, and records them through record_benchmark_result.py under the
current config id. Each new record keeps the original model, suite, run class, methodology and
run time, so it sorts beside the run it re-scores. Strict rows are never re-recorded.

Dry run by default; --apply writes. Re-running is safe: a (model, suite, test_id) that already
has a record under the target config id is skipped. Run it only while no suite is appending
records, since it regenerates the reference and scoreboard at the end.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = Path(__file__).resolve().parent
HISTORY = Path("/mnt/shared/logs/benchmarks/bench-reasoning/history")
CONFIG_ID = "lm-eval-0.4.11-reasoning-extract-v5"
CONFIG = {"lm_eval": "0.4.11", "extraction": "reasoning-v5", "bbh_stop": "newline Q:", "bbh_max_gen_toks": 1024,
          "flexible_rows": ["bbh_flexible", "drop_flexible", "mmlu_pro_flexible", "gsm8k_flexible"],
          "rescored_from_samples": True}
FLEXIBLE = set(CONFIG["flexible_rows"])
# The strict row whose run_at dates each task of the original run.
STRICT_ROW = {"gsm8k": "gsm8k_strict", "bbh": "bbh", "drop": "drop_em",
              "mmlu_pro": "mmlu_pro_exact_match_custom-extract"}


def load_extractor():
    spec = importlib.util.spec_from_file_location("extract_reasoning_results", ACTIVE / "extract_reasoning_results.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_records(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def history_dir(history: Path, model: str, suite: str) -> Path | None:
    exact = history / f"bench-reasoning_{model.replace(':', '_')}_{suite}"
    if exact.is_dir():
        return exact
    matches = [d for d in history.glob(f"*_{suite}") if d.is_dir()]
    return matches[0] if len(matches) == 1 else None


def task_rows(extractor, run_dir: Path, task: str) -> list[tuple]:
    """Flexible rows from the newest result file of one task, scored from its samples."""
    files = sorted((run_dir / task).glob("**/results_*.json"))
    if not files:
        return []
    stamp = files[-1].stem.removeprefix("results_")
    samples = [json.loads(line) for f in sorted(files[-1].parent.glob(f"samples_*_{stamp}.jsonl"))
               for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not samples:
        return []
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    return [row for row in extractor.extract_rows(task, data, samples) if row[0] in FLEXIBLE]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--records", default=str(ROOT / "results/model_benchmark_records.jsonl"))
    ap.add_argument("--history", default=str(HISTORY))
    ap.add_argument("--apply", action="store_true", help="write records (default: print what would be recorded)")
    args = ap.parse_args()

    records_path = Path(args.records).resolve()
    history = Path(args.history)
    extractor = load_extractor()
    records = [r for r in read_records(records_path) if r.get("harness") == "bench-reasoning"]
    done = {(r["model"], r["suite"], r["test_id"]) for r in records
            if (r.get("runtime") or {}).get("config_id") == CONFIG_ID}

    # One source record per (model, suite, task): the newest strict row, for run_at and context.
    sources: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in records:
        if r.get("status") != "success" or not r.get("run_class"):
            continue
        for task, strict_id in STRICT_ROW.items():
            if r.get("test_id") == strict_id:
                key = (r["model"], r["suite"], task)
                if key not in sources or r["run_at"] > sources[key]["run_at"]:
                    sources[key] = r

    planned = skipped = missing = 0
    for (model, suite, task), src in sorted(sources.items()):
        run_dir = history_dir(history, model, suite)
        if run_dir is None:
            missing += 1
            continue
        for row in task_rows(extractor, run_dir, task):
            test_id, score, metric, raw, normalized, compat, failures, count, notes = row
            if (model, suite, test_id) in done:
                skipped += 1
                continue
            planned += 1
            print(f"{model:28} {suite[:48]:48} {test_id:18} {float(score):.3f} n={count} {notes}")
            if not args.apply:
                continue
            method = src.get("methodology") or {}
            cmd = [sys.executable, str(ACTIVE / "record_benchmark_result.py"),
                   "--model", model, "--test-id", test_id, "--score", str(score),
                   "--raw-harness-score", str(raw), "--normalized-answer-score", str(normalized),
                   "--metric", metric, "--run-class", src["run_class"], "--sample-count", str(count),
                   "--format-compatibility", compat, "--extractor-failure-count", str(failures),
                   "--harness", "bench-reasoning", "--suite", suite,
                   "--methodology-id", method.get("id", ""), "--methodology-version", method.get("version", ""),
                   "--comparison-group", method.get("comparison_group", ""),
                   "--records", str(records_path), "--config-id", CONFIG_ID,
                   "--config-json", json.dumps(CONFIG, separators=(",", ":")),
                   "--run-at", src["run_at"], "--notes", f"{notes}; rescored from samples", "--no-refresh"]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

    print(f"\n{'recorded' if args.apply else 'would record'} {planned}; already rescored {skipped}; "
          f"no history dir for {missing} suite-tasks")
    if args.apply and planned:
        results = records_path.parent
        for script, out in (("build_benchmark_reference.py", "MODEL_BENCHMARK_REFERENCE.md"),
                            ("build_model_library_scoreboard.py", "model_library_scoreboard.json"),
                            ("build_methodology_history.py", "model_methodology_history.json")):
            subprocess.run([sys.executable, str(ACTIVE / script), "--records", str(records_path),
                            "--output", str(results / out)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
