#!/usr/bin/env python3
"""Re-grade past custom_json_schema_strict runs with the current grader and record the new scores.

When the JSON schema grader changed (bench-pipeline methodology 2.1.0, 2026-10-23: the priority value is
no longer graded, action keywords match across spaces and hyphens), the responses saved in each run's
result.json can be graded again without re-running the model: the prompts did not change. This walks
the custom_json_schema_strict rows in model_benchmark_records.jsonl, finds each run's result.json from
the result_path in its notes, re-grades every saved response against the current cases.json, and
records the score through record_benchmark_result.py under methodology 2.1.0. Each new record keeps the
original model, suite, run class and run time, so it sorts beside the run it re-grades and replaces it
in the scoreboard (benchmark_records.selection_key prefers the newer methodology on a tie).

Dry run by default; --apply writes. Re-running is safe: a (model, suite) that already has a 2.1.0 row is
skipped. Run it only while no suite is appending records, since it regenerates the reference and
scoreboard at the end.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = Path(__file__).resolve().parent
HISTORY = Path("/mnt/shared/logs/benchmarks/bench-pipeline/history")
TEST_ID = "custom_json_schema_strict"
METHODOLOGY = ("bench-pipeline/local-custom", "2.1.0", "pipeline-local-custom-v2")
CONFIG = {"grading": "json-schema-v2", "rescored_from_responses": True}


def load_grader():
    spec = importlib.util.spec_from_file_location("run_local_custom_task", ACTIVE / "run_local_custom_task.py")
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


def result_file(history: Path, notes: str) -> Path | None:
    match = re.search(r"result_path=/results/([^/;\s]+)/result\.json", notes or "")
    if not match:
        return None
    path = history / match.group(1) / "result.json"
    return path if path.is_file() else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--records", default=str(ROOT / "results/model_benchmark_records.jsonl"))
    ap.add_argument("--history", default=str(HISTORY))
    ap.add_argument("--cases", default=str(ROOT / "custom_tasks/cases.json"))
    ap.add_argument("--apply", action="store_true", help="write records (default: print what would be recorded)")
    args = ap.parse_args()

    records_path = Path(args.records).resolve()
    history = Path(args.history)
    grader = load_grader()
    cases = {c["name"]: c for c in grader.load_cases(Path(args.cases)).get(TEST_ID, {}).get("cases", [])}
    rows = [r for r in read_records(records_path) if r.get("test_id") == TEST_ID and r.get("status") == "success"]
    done = {(r["model"], r["suite"]) for r in rows if (r.get("methodology") or {}).get("version") == METHODOLOGY[1]}

    planned = skipped = missing = 0
    for src in sorted(rows, key=lambda r: (r["model"], r["suite"], r["run_at"])):
        if (src.get("methodology") or {}).get("version") == METHODOLOGY[1]:
            continue
        if (src["model"], src["suite"]) in done:
            skipped += 1
            continue
        path = result_file(history, src.get("notes", ""))
        if path is None:
            missing += 1
            print(f"{src['model']:28} {src['suite'][:48]:48} no result.json")
            continue
        saved = json.loads(path.read_text(encoding="utf-8")).get("cases", [])
        graded = [grader.grade_case(TEST_ID, cases[c["name"]], c.get("response", ""))[0]
                  for c in saved if c.get("name") in cases]
        if not graded:
            missing += 1
            continue
        passes, total = sum(graded), len(graded)
        score = passes / total
        planned += 1
        done.add((src["model"], src["suite"]))
        print(f"{src['model']:28} {src['suite'][:48]:48} {src.get('score', 0):.3f} -> {score:.3f} ({passes}/{total})")
        if not args.apply:
            continue
        notes = f"passes={passes}; total={total}; result_path=/results/{path.parent.name}/result.json; regraded from responses"
        cmd = [sys.executable, str(ACTIVE / "record_benchmark_result.py"),
               "--model", src["model"], "--test-id", TEST_ID, "--score", str(score),
               "--raw-harness-score", str(score), "--metric", src.get("metric") or "score",
               "--run-class", src["run_class"], "--sample-count", str(total),
               "--format-compatibility", src.get("format_compatibility") or "unknown",
               "--harness", "bench-pipeline", "--suite", src["suite"],
               "--methodology-id", METHODOLOGY[0], "--methodology-version", METHODOLOGY[1],
               "--comparison-group", METHODOLOGY[2],
               "--records", str(records_path), "--config-id", (src.get("runtime") or {}).get("config_id", ""),
               "--config-json", json.dumps(CONFIG, separators=(",", ":")),
               "--run-at", src["run_at"], "--notes", notes, "--no-refresh"]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

    print(f"\n{'recorded' if args.apply else 'would record'} {planned}; already regraded {skipped}; "
          f"no result.json for {missing}")
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
