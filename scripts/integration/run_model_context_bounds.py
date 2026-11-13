#!/usr/bin/env python3
"""Check a newly imported model's minimum and maximum loads on chosen GPU groups.

The compact group is the smallest useful footprint. The ceiling group is the
larger placement allowed for long context. Each distinct group gets manager
min/max fits followed by real load/unload checks at both contexts. No quality
or depth probe runs here; those are separate gates after the smoke tests.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import run_context_capacity_min_sizing as minimum
import run_context_capacity_sizing as maximum
from hardware_inventory import scan_cards, require_ids, check_planned_power

ROOT = Path(__file__).resolve().parents[2]


def parse_cards(value: str) -> list[int]:
    try:
        cards = [int(part) for part in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("GPU indices must be comma-separated integers") from exc
    if not cards or len(set(cards)) != len(cards) or any(card < 0 for card in cards):
        raise argparse.ArgumentTypeError("GPU indices must be unique nonnegative integers")
    return cards


def required_fit(model: str, cards: list[int], mode: str) -> dict:
    rc, plan = maximum.fit(model, cards, mode)
    if rc or plan.get("fits") is not True:
        raise RuntimeError(f"manager {mode} fit failed: {plan.get('reason') or plan.get('error')}")
    if plan.get("gpus") != cards:
        raise RuntimeError(f"manager {mode} fit changed GPUs: {plan.get('gpus')}")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", help="registered short model id")
    parser.add_argument("--compact-gpus", type=parse_cards, required=True,
                        help="smallest useful card group, e.g. 1,2 or 0,1,2,3,4,5")
    parser.add_argument("--ceiling-gpus", type=parse_cards, required=True,
                        help="larger card group for the longest context")
    parser.add_argument("--run-id", required=True, help="unique id for checkpoint and manager report")
    parser.add_argument("--output", type=Path, required=True, help="durable result directory")
    args = parser.parse_args()
    if not set(args.compact_gpus).issubset(args.ceiling_gpus):
        parser.error("compact GPUs must be a subset of ceiling GPUs")
    inventory = scan_cards()
    require_ids(args.ceiling_gpus, inventory)
    registry = json.loads((ROOT / "model_registry.json").read_text(encoding="utf-8"))
    model = registry.get("models", {}).get(args.model)
    if not model:
        parser.error(f"model {args.model!r} is not in model_registry.json")
    bounds = (model.get("profiles", {}).get("default", {}).get("context_bounds") or {})
    trained = int(bounds.get("max") or 0)
    if trained < 1:
        parser.error("default profile needs context_bounds.max before sizing")

    groups = [("compact", args.compact_gpus)]
    if args.ceiling_gpus != args.compact_gpus:
        groups.append(("ceiling", args.ceiling_gpus))
    else:
        groups[0] = ("compact_and_ceiling", args.compact_gpus)
    args.output.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output / "checkpoint.json"
    state = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {
        "run": args.run_id, "model": args.model, "started_at": maximum.stamp(), "groups": {}}
    if state["run"] != args.run_id or state["model"] != args.model:
        raise RuntimeError("checkpoint belongs to a different run or model")

    for label, cards in groups:
        row = state["groups"].get(label, {})
        if row.get("status") == "passed":
            continue
        check_planned_power(args.ceiling_gpus)
        row = {"status": "running", "gpus": cards, "started_at": maximum.stamp()}
        state["groups"][label] = row
        maximum.write_json(checkpoint, state)
        print(f"{label}: manager min/max fit on GPUs {cards}", flush=True)
        try:
            min_plan = required_fit(args.model, cards, "min")
            max_plan = required_fit(args.model, cards, "max")
            min_ctx, max_ctx = int(min_plan["ctx"]), int(max_plan["ctx"])
            if min_ctx > max_ctx or max_ctx > trained:
                raise RuntimeError(f"invalid context range {min_ctx}..{max_ctx}, trained {trained}")
            row.update(min_fit=min_plan, max_fit=max_plan,
                       min_ctx=min_ctx, max_ctx=max_ctx, trained_ctx=trained)
            case = {"id": f"{args.run_id}__{label}", "model": args.model, "gpus": cards,
                    "ctx": max_ctx, "trained_ctx": trained, "target": label}
            if min_ctx == max_ctx:
                row["min_load"] = {"shared_with_max": True}
            else:
                check_planned_power(args.ceiling_gpus)
                row["min_load"] = minimum.run_case(case, max_ctx)
                maximum.write_json(checkpoint, state)
                if row["min_load"].get("error"):
                    raise RuntimeError(f"minimum load: {row['min_load']['error']}")
            check_planned_power(args.ceiling_gpus)
            row["max_load"] = maximum.check_case(case)
            maximum.write_json(checkpoint, state)
            if row["max_load"].get("error"):
                raise RuntimeError(f"maximum load: {row['max_load']['error']}")
            row["status"] = "passed"
            print(f"{label}: passed, ctx {min_ctx}..{max_ctx}", flush=True)
        except Exception as exc:
            row["status"] = "failed"
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"{label}: failed, {row['error']}", flush=True)
        row["finished_at"] = maximum.stamp()
        maximum.write_json(args.output / "receipts" / f"{label}.json", row)
        maximum.write_json(checkpoint, state)
        if row["status"] != "passed":
            break

    failed = [label for label, _ in groups if state["groups"].get(label, {}).get("status") != "passed"]
    terminal = {"run": args.run_id, "model": args.model, "finished_at": maximum.stamp(),
                "groups": len(groups), "passed": len(groups) - len(failed), "failed": failed}
    maximum.write_json(args.output / "terminal.json", terminal)
    lines = ["# New model context bounds", "", f"Model: `{args.model}`. Run: `{args.run_id}`.",
             "Manager min/max fits and real load/unload checks; no depth or quality probes.", "",
             "| Group | GPUs | Min ctx/load s | Max ctx/load s | Status |",
             "|---|---|---:|---:|---|"]
    for label, cards in groups:
        row = state["groups"].get(label, {})
        min_load = row.get("min_load") or {}
        max_load = row.get("max_load") or {}
        min_seconds = (min_load.get("load") or {}).get("seconds", "—")
        if min_load.get("shared_with_max"):
            min_seconds = "same as max"
        lines.append(f"| {label} | {','.join(map(str, cards))} | "
                     f"{row.get('min_ctx', '—')} / {min_seconds} | "
                     f"{row.get('max_ctx', '—')} / {(max_load.get('load') or {}).get('seconds', '—')} | "
                     f"{row.get('status', 'pending')} |")
    (args.output / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(terminal), flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
