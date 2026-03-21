"""
DaedalMap LLM Benchmark Runner

Tests local models via llama.cpp OpenAI-compatible API on the chat layer in isolation.
No live data or server connection required - scores raw model JSON output only.

Scoring per case:
  json_valid        - response is parseable JSON with a "type" field
  type_correct      - "type" matches expected_type
  source_hit        - at least one expected_source_id appears in order items (orders only)
  source_valid      - all source_ids in order items are in the known catalog
  no_hallucination  - none of must_not_hallucinate source_ids appear in response
  latency_ms        - time from request send to response received
  prompt_tokens     - from API usage field if available
  completion_tokens - from API usage field if available

Usage:
  python llm_benchmark_runner.py --suite llm_benchmark_v1.json --model-tag phi3-3.8b
  python llm_benchmark_runner.py --suite llm_benchmark_v1.json --model-tag gemma2-2b --api-base http://localhost:8081
  python llm_benchmark_runner.py --suite llm_benchmark_v1.json --model-tag qwen2.5-7b --limit 10
  python llm_benchmark_runner.py --compare results/llm_results_phi3*.jsonl results/llm_results_gemma2*.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    import msgpack as _msgpack
    _MSGPACK_AVAILABLE = True
except ImportError:
    _MSGPACK_AVAILABLE = False

from benchmark_prompt import build_benchmark_prompt, BENCHMARK_CATALOG


def _load_valid_source_ids() -> set:
    """Load valid source IDs from benchmark_catalog.json. Falls back to hardcoded set."""
    catalog_path = Path(__file__).parent / "benchmark_catalog.json"
    if catalog_path.exists():
        with open(catalog_path, encoding="utf-8") as f:
            catalog = json.load(f)
        ids = {s["source_id"] for s in catalog.get("sources", [])}
        if ids:
            return ids
    # Fallback if catalog file is missing
    return {
        "census", "fema_nri", "tornadoes",
        "abs_population",
        "earthquakes", "hurricanes", "tsunamis", "volcanoes", "wildfires",
        "floods", "landslides", "owid_co2", "imf_bop", "worldpop",
        "fx_usd_historical",
        "un_sdg_01", "un_sdg_02", "un_sdg_03", "un_sdg_06",
        "un_sdg_07", "un_sdg_08", "un_sdg_13",
    }


# Valid source_ids loaded from benchmark_catalog.json (single source of truth)
VALID_SOURCE_IDS = _load_valid_source_ids()

# Types that include order items to check
ORDER_TYPES = {"order"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DaedalMap LLM Chat Layer Benchmark Runner")
    parser.add_argument("--suite", default="llm_benchmark_v1.json", help="Suite JSON file path")
    parser.add_argument("--model-tag", required=False, default="unknown", help="Label for this model run (e.g. phi3-3.8b-q4)")
    parser.add_argument("--api-base", default="http://localhost:8080", help="llama.cpp OpenAI-compatible base URL")
    parser.add_argument("--model-name", default="local", help="Model name to pass in API request (some servers require it)")
    parser.add_argument("--temperature", type=float, default=0.1, help="Sampling temperature (lower = more deterministic)")
    parser.add_argument("--max-tokens", type=int, default=400, help="Max tokens in response")
    parser.add_argument("--limit", type=int, default=0, help="Run first N cases only (0 = all)")
    parser.add_argument("--category", default="", help="Filter to a single category (json_discipline, type_routing, source_grounding, catalog_discipline, geographic_precision, multi_source)")
    parser.add_argument("--requires", default="", help="Filter to cases with this requires value: catalog or data_s3")
    parser.add_argument("--out-dir", default="results", help="Output directory for JSONL and CSV")
    parser.add_argument("--summary-out", default="", help="Optional path to write machine-readable summary JSON")
    parser.add_argument("--timeout", type=int, default=60, help="Per-request timeout in seconds")
    parser.add_argument("--daedalmap-url", default="", help="DaedalMap API base URL for execution validation (e.g. https://daedalmap.io). Only used for requires=data_s3 order cases.")
    parser.add_argument("--execute", action="store_true", help="Run execution validation against --daedalmap-url for data_s3 order cases.")
    parser.add_argument("--auth-token", default="", help="Optional bearer token for DaedalMap API requests (needed if catalog requires entitlement).")
    parser.add_argument("--compare", nargs="+", metavar="JSONL", help="Compare mode: pass two or more result JSONL files to print a side-by-side table")
    return parser.parse_args()


def load_suite(suite_path: str) -> dict:
    path = Path(suite_path)
    if not path.is_absolute():
        path = Path(__file__).parent / suite_path
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def call_model(api_base: str, model_name: str, system_prompt: str, query: str,
               temperature: float, max_tokens: int, timeout: int) -> tuple[str, float, int, int]:
    """
    Call llama.cpp OpenAI-compatible endpoint.
    Returns (raw_text, latency_ms, prompt_tokens, completion_tokens).
    """
    url = api_base.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    t0 = time.monotonic()
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return "[TIMEOUT]", (time.monotonic() - t0) * 1000, 0, 0
    except requests.exceptions.RequestException as e:
        return f"[REQUEST_ERROR: {e}]", (time.monotonic() - t0) * 1000, 0, 0

    latency_ms = (time.monotonic() - t0) * 1000
    data = resp.json()

    raw_text = ""
    try:
        raw_text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raw_text = "[EMPTY_RESPONSE]"

    usage = data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    return raw_text, latency_ms, prompt_tokens, completion_tokens


def extract_json(raw: str) -> dict | None:
    """Extract JSON from model response - handles fenced and bare JSON."""
    if not raw or raw.startswith("["):
        return None

    # Try fenced ```json ... ```
    if "```json" in raw:
        try:
            inner = raw.split("```json")[1].split("```")[0].strip()
            return json.loads(inner)
        except (json.JSONDecodeError, IndexError):
            pass

    # Try fenced ``` ... ```
    if "```" in raw:
        try:
            inner = raw.split("```")[1].split("```")[0].strip()
            if inner.startswith("{"):
                return json.loads(inner)
        except (json.JSONDecodeError, IndexError):
            pass

    # Try bare JSON object
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def score_case(case: dict, parsed: dict | None, raw: str) -> dict:
    """Score a single case against its expected outputs."""
    expected_type = case.get("expected_type", "")
    expected_sources = set(case.get("expected_source_ids", []))
    must_not = set(case.get("must_not_hallucinate", []))
    clarify_ok = case.get("clarify_ok", False)

    scores = {
        "json_valid": False,
        "type_field_present": False,
        "type_correct": False,
        "source_hit": None,       # None = not applicable
        "source_valid": None,
        "no_hallucination": True,
        "failure_tags": [],
    }

    if parsed is None:
        scores["failure_tags"].append("no_json")
        # Still check hallucination in raw text
        for bad_src in must_not:
            if bad_src in raw:
                scores["no_hallucination"] = False
                scores["failure_tags"].append(f"hallucinated:{bad_src}")
        return scores

    scores["json_valid"] = True

    response_type = parsed.get("type")
    if response_type:
        scores["type_field_present"] = True
    else:
        scores["failure_tags"].append("no_type_field")

    # Type correctness - clarify_ok means clarify is also acceptable
    if response_type == expected_type:
        scores["type_correct"] = True
    elif clarify_ok and response_type == "clarify":
        scores["type_correct"] = True
    else:
        if response_type and expected_type:
            scores["failure_tags"].append(f"wrong_type:{response_type}_expected:{expected_type}")

    # Source checks only apply to order responses
    if response_type in ORDER_TYPES:
        items = parsed.get("items", [])
        used_sources = {item.get("source_id", "") for item in items if item.get("source_id")}

        if expected_sources:
            scores["source_hit"] = bool(used_sources & expected_sources)
            if not scores["source_hit"]:
                scores["failure_tags"].append(f"missed_sources:{','.join(expected_sources)}")

        invalid = used_sources - VALID_SOURCE_IDS
        scores["source_valid"] = len(invalid) == 0
        if invalid:
            scores["failure_tags"].append(f"invalid_sources:{','.join(sorted(invalid))}")

        # Hallucination check: any must_not sources in used_sources or raw text
        for bad_src in must_not:
            if bad_src in used_sources or bad_src in raw:
                scores["no_hallucination"] = False
                scores["failure_tags"].append(f"hallucinated:{bad_src}")
    else:
        # For non-order responses, check raw text for hallucinated source_ids
        for bad_src in must_not:
            if bad_src in raw:
                scores["no_hallucination"] = False
                scores["failure_tags"].append(f"hallucinated:{bad_src}")

    return scores


def derive_status(scores: dict) -> str:
    """PASS / PARTIAL / FAIL from score dict."""
    if not scores["json_valid"]:
        return "FAIL"
    if not scores["type_correct"]:
        return "FAIL"
    if scores["source_valid"] is False:
        return "FAIL"
    if not scores["no_hallucination"]:
        return "FAIL"
    if scores["source_hit"] is False:
        return "PARTIAL"
    return "PASS"


def build_summary(results: list[dict], model_tag: str, suite_id: str, category: str = "", requires: str = "") -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    partial = sum(1 for r in results if r["status"] == "PARTIAL")
    failed = sum(1 for r in results if r["status"] == "FAIL")

    json_valid = sum(1 for r in results if r["json_valid"])
    type_correct = sum(1 for r in results if r["type_correct"])
    no_halluc = sum(1 for r in results if r["no_hallucination"])

    source_hit_cases = [r for r in results if r["source_hit"] is not None]
    source_valid_cases = [r for r in results if r["source_valid"] is not None]

    latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2] if latencies_sorted else 0
    p95_idx = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[min(p95_idx, len(latencies_sorted) - 1)] if latencies_sorted else 0

    categories = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"pass": 0, "partial": 0, "fail": 0, "total": 0}
        categories[cat]["total"] += 1
        categories[cat][r["status"].lower()] += 1

    source_hit_rate = None
    if source_hit_cases:
        source_hit_rate = sum(1 for r in source_hit_cases if r["source_hit"]) / len(source_hit_cases)

    source_valid_rate = None
    if source_valid_cases:
        source_valid_rate = sum(1 for r in source_valid_cases if r["source_valid"]) / len(source_valid_cases)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite_id": suite_id,
        "model_tag": model_tag,
        "category_filter": category,
        "requires_filter": requires,
        "total_cases": total,
        "pass_count": passed,
        "partial_count": partial,
        "fail_count": failed,
        "pass_rate": (passed / total) if total else 0.0,
        "json_valid_rate": (json_valid / total) if total else 0.0,
        "type_correct_rate": (type_correct / total) if total else 0.0,
        "source_hit_rate": source_hit_rate,
        "source_hit_applicable": len(source_hit_cases),
        "source_valid_rate": source_valid_rate,
        "source_valid_applicable": len(source_valid_cases),
        "no_halluc_rate": (no_halluc / total) if total else 0.0,
        "latency_p50_ms": p50,
        "latency_p95_ms": p95,
        "categories": categories,
    }


def execute_order(daedalmap_url: str, items: list, session_id: str, auth_token: str, timeout: int) -> dict:
    """
    POST a confirmed_order to the DaedalMap /chat endpoint and return execution metadata.
    Returns dict with keys: exec_valid, exec_type, exec_count, exec_error.
    """
    if not _MSGPACK_AVAILABLE:
        return {"exec_valid": None, "exec_type": None, "exec_count": None, "exec_error": "msgpack not installed"}

    url = daedalmap_url.rstrip("/") + "/chat"
    payload = {"confirmed_order": {"items": items}, "sessionId": session_id}
    body = _msgpack.packb(payload, use_bin_type=True)
    headers = {"content-type": "application/msgpack"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        resp = requests.post(url, data=body, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = _msgpack.unpackb(resp.content, raw=False, strict_map_key=False)
    except Exception as e:
        return {"exec_valid": False, "exec_type": "error", "exec_count": None, "exec_error": str(e)}

    exec_type = data.get("type")
    exec_count = data.get("count") if isinstance(data.get("count"), int) else None
    exec_error = data.get("error") or ""

    success_types = {"data", "events", "mixed_order", "already_loaded"}
    exec_valid = (exec_type in success_types) and (exec_count is None or exec_count > 0)

    return {
        "exec_valid": exec_valid,
        "exec_type": exec_type,
        "exec_count": exec_count,
        "exec_error": exec_error,
    }


def run_benchmark(args: argparse.Namespace) -> tuple[list[dict], dict[str, Any]]:
    suite = load_suite(args.suite)
    cases = suite["cases"]

    if args.category:
        cases = [c for c in cases if c.get("category") == args.category]

    if args.requires:
        cases = [c for c in cases if c.get("requires", "") == args.requires]

    if args.limit and args.limit > 0:
        cases = cases[:args.limit]

    system_prompt = build_benchmark_prompt()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    model_tag = args.model_tag.replace(" ", "_")

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = Path(__file__).parent / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = out_dir / f"llm_results_{model_tag}_{run_id}.jsonl"
    csv_path = out_dir / f"llm_results_{model_tag}_{run_id}.csv"

    csv_fields = [
        "case_id", "category", "priority", "requires", "model_tag", "status",
        "json_valid", "type_correct", "source_hit", "source_valid",
        "no_hallucination", "latency_ms", "prompt_tokens", "completion_tokens",
        "expected_type", "actual_type", "failure_tags",
        "exec_valid", "exec_type", "exec_count", "exec_error",
        "query",
    ]

    results = []
    total = len(cases)

    print(f"Suite:      {suite['suite_id']} ({total} cases)")
    print(f"Model tag:  {model_tag}")
    print(f"API base:   {args.api_base}")
    print(f"Output:     {jsonl_path.name}")
    print()

    with open(jsonl_path, "w", encoding="utf-8") as jf, \
         open(csv_path, "w", newline="", encoding="utf-8") as cf:

        writer = csv.DictWriter(cf, fieldnames=csv_fields)
        writer.writeheader()

        for i, case in enumerate(cases, 1):
            case_id = case["case_id"]
            query = case["query"]

            print(f"[{i:02d}/{total}] {case_id}  {query[:60]}", end=" ... ", flush=True)

            raw, latency_ms, prompt_tokens, completion_tokens = call_model(
                api_base=args.api_base,
                model_name=args.model_name,
                system_prompt=system_prompt,
                query=query,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
            )

            parsed = extract_json(raw)
            scores = score_case(case, parsed, raw)
            status = derive_status(scores)
            actual_type = parsed.get("type", "") if parsed else ""

            # Execution validation for data_s3 cases when --execute and --daedalmap-url are set
            exec_result = {"exec_valid": None, "exec_type": None, "exec_count": None, "exec_error": ""}
            if (args.execute and args.daedalmap_url
                    and case.get("requires") == "data_s3"
                    and actual_type == "order"
                    and parsed):
                items = parsed.get("items", [])
                if items:
                    exec_result = execute_order(
                        daedalmap_url=args.daedalmap_url,
                        items=items,
                        session_id=f"bench-{run_id}-{case_id}",
                        auth_token=args.auth_token,
                        timeout=args.timeout,
                    )

            row = {
                "case_id": case_id,
                "category": case.get("category", ""),
                "priority": case.get("priority", ""),
                "requires": case.get("requires", ""),
                "model_tag": model_tag,
                "status": status,
                "json_valid": scores["json_valid"],
                "type_correct": scores["type_correct"],
                "source_hit": scores["source_hit"],
                "source_valid": scores["source_valid"],
                "no_hallucination": scores["no_hallucination"],
                "latency_ms": round(latency_ms, 1),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "expected_type": case.get("expected_type", ""),
                "actual_type": actual_type,
                "failure_tags": "|".join(scores["failure_tags"]),
                "exec_valid": exec_result["exec_valid"],
                "exec_type": exec_result["exec_type"],
                "exec_count": exec_result["exec_count"],
                "exec_error": exec_result["exec_error"],
                "query": query,
                "raw_response": raw,
                "parsed_response": parsed,
                "notes": case.get("notes", ""),
            }

            results.append(row)

            # JSONL row (full data including raw)
            jf.write(json.dumps(row, ensure_ascii=False) + "\n")
            jf.flush()

            # CSV row (no raw response - too wide)
            csv_row = {k: row[k] for k in csv_fields}
            writer.writerow(csv_row)
            cf.flush()

            status_str = f"{status:<8}"
            latency_str = f"{latency_ms:6.0f}ms"
            exec_str = ""
            if exec_result["exec_valid"] is not None:
                ev = exec_result["exec_valid"]
                ec = exec_result["exec_count"]
                exec_str = f"  exec={'OK' if ev else 'FAIL'}" + (f"({ec})" if ec is not None else "")
            print(f"{status_str} {latency_str}  {actual_type or '(no json)'}{exec_str}")

    print()
    print_summary(results, model_tag)
    print(f"\nResults: {jsonl_path}")
    print(f"CSV:     {csv_path}")

    summary = build_summary(
        results,
        model_tag=model_tag,
        suite_id=str(suite.get("suite_id", "")),
        category=args.category,
        requires=args.requires,
    )
    if args.summary_out:
        summary_path = Path(args.summary_out)
        if not summary_path.is_absolute():
            summary_path = Path.cwd() / summary_path
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    return results, summary


def print_summary(results: list[dict], model_tag: str):
    total = len(results)
    if total == 0:
        print("No results.")
        return

    passed = sum(1 for r in results if r["status"] == "PASS")
    partial = sum(1 for r in results if r["status"] == "PARTIAL")
    failed = sum(1 for r in results if r["status"] == "FAIL")

    json_valid = sum(1 for r in results if r["json_valid"])
    type_correct = sum(1 for r in results if r["type_correct"])
    no_halluc = sum(1 for r in results if r["no_hallucination"])

    source_hit_cases = [r for r in results if r["source_hit"] is not None]
    source_valid_cases = [r for r in results if r["source_valid"] is not None]

    latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2] if latencies_sorted else 0
    p95_idx = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[min(p95_idx, len(latencies_sorted) - 1)] if latencies_sorted else 0

    print(f"=== Results: {model_tag} ===")
    print(f"  Total cases:       {total}")
    print(f"  PASS:              {passed} ({100*passed//total}%)")
    print(f"  PARTIAL:           {partial} ({100*partial//total}%)")
    print(f"  FAIL:              {failed} ({100*failed//total}%)")
    print()
    print(f"  json_valid_rate:   {100*json_valid//total}%  ({json_valid}/{total})")
    print(f"  type_correct_rate: {100*type_correct//total}%  ({type_correct}/{total})")
    if source_hit_cases:
        src_hit = sum(1 for r in source_hit_cases if r["source_hit"])
        print(f"  source_hit_rate:   {100*src_hit//len(source_hit_cases)}%  ({src_hit}/{len(source_hit_cases)} applicable)")
    if source_valid_cases:
        src_val = sum(1 for r in source_valid_cases if r["source_valid"])
        print(f"  source_valid_rate: {100*src_val//len(source_valid_cases)}%  ({src_val}/{len(source_valid_cases)} applicable)")
    print(f"  no_halluc_rate:    {100*no_halluc//total}%  ({no_halluc}/{total})")
    print()
    print(f"  latency p50:       {p50:.0f}ms")
    print(f"  latency p95:       {p95:.0f}ms")

    # Category breakdown
    categories = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"pass": 0, "partial": 0, "fail": 0, "total": 0}
        categories[cat]["total"] += 1
        categories[cat][r["status"].lower()] += 1

    print()
    print("  Category breakdown:")
    for cat, counts in sorted(categories.items()):
        t = counts["total"]
        p = counts["pass"]
        print(f"    {cat:<25} PASS={p}/{t}  ({100*p//t}%)")

    # Failures
    failures = [r for r in results if r["status"] in ("FAIL", "PARTIAL")]
    if failures:
        print()
        print("  Failures and partials:")
        for r in failures:
            tags = r.get("failure_tags", "") or "-"
            print(f"    {r['case_id']:<12} {r['status']:<8} {tags}")


def compare_runs(jsonl_paths: list[str]):
    """Print a side-by-side comparison table from multiple result files."""
    runs = {}
    for path in jsonl_paths:
        results = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    results.append(json.loads(line))
        if results:
            tag = results[0].get("model_tag", Path(path).stem)
            runs[tag] = results

    if not runs:
        print("No results loaded.")
        return

    # Collect all case_ids in order
    all_case_ids = []
    seen = set()
    for results in runs.values():
        for r in results:
            cid = r["case_id"]
            if cid not in seen:
                all_case_ids.append(cid)
                seen.add(cid)

    tags = list(runs.keys())
    col_w = 10

    # Header
    header = f"{'case_id':<12}" + "".join(f"{t[:col_w]:<{col_w+2}}" for t in tags)
    print(header)
    print("-" * len(header))

    for cid in all_case_ids:
        row = f"{cid:<12}"
        for tag in tags:
            result_map = {r["case_id"]: r for r in runs[tag]}
            r = result_map.get(cid)
            if r is None:
                row += f"{'N/A':<{col_w+2}}"
            else:
                cell = r["status"]
                if not r["json_valid"]:
                    cell = "NO_JSON"
                row += f"{cell:<{col_w+2}}"
        print(row)

    print()
    print("=== Summary ===")
    summary_metrics = [
        ("json_valid_rate", lambda rs: f"{100*sum(1 for r in rs if r['json_valid'])//len(rs)}%"),
        ("type_correct_rate", lambda rs: f"{100*sum(1 for r in rs if r['type_correct'])//len(rs)}%"),
        ("no_halluc_rate", lambda rs: f"{100*sum(1 for r in rs if r['no_hallucination'])//len(rs)}%"),
        ("pass_rate", lambda rs: f"{100*sum(1 for r in rs if r['status']=='PASS')//len(rs)}%"),
        ("p50_latency", lambda rs: f"{sorted(r['latency_ms'] for r in rs)[len(rs)//2]:.0f}ms"),
    ]

    metric_col = 20
    print(f"{'metric':<{metric_col}}" + "".join(f"{t[:col_w]:<{col_w+2}}" for t in tags))
    print("-" * (metric_col + (col_w + 2) * len(tags)))

    for label, fn in summary_metrics:
        row = f"{label:<{metric_col}}"
        for tag in tags:
            rs = runs[tag]
            try:
                val = fn(rs)
            except Exception:
                val = "ERR"
            row += f"{val:<{col_w+2}}"
        print(row)


def main():
    args = parse_args()

    if args.compare:
        compare_runs(args.compare)
        return

    if not args.model_tag or args.model_tag == "unknown":
        print("WARNING: --model-tag not set. Use --model-tag phi3-3.8b-q4 to label results.")
        print()

    run_benchmark(args)


if __name__ == "__main__":
    main()
