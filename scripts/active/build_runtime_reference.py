#!/usr/bin/env python3
"""Build results/RUNTIME_REFERENCE.md from every record in results/runtime_experiments/.

The runtime counterpart of MODEL_BENCHMARK_REFERENCE.md: speed, context and power measurements, one table per
record kind (capacity runs, runtime characterizations, split scaling) and an index of the rest. Generated: edit
the records or this script, never the output. The capacity and runtime-characterization tools rebuild it after
each record; run it by hand after adding any other record.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RX = ROOT / "results" / "runtime_experiments"
OUT = ROOT / "results" / "RUNTIME_REFERENCE.md"


def cards(gpus) -> str:
    gpus = [int(g) for g in gpus or []]
    if not gpus:
        return "-"
    if gpus == [0]:
        return "3090"
    names = ["3090" if g == 0 else f"1060 #{g}" for g in gpus]
    return " + ".join(names) if len(gpus) <= 2 else f"{len(gpus)} cards ({','.join(str(g) for g in gpus)})"


def num(v, fmt="{:.1f}") -> str:
    return "-" if v in (None, "") else fmt.format(float(v))


def capacity_rows(records: list[tuple[str, dict]]) -> list[str]:
    out = ["| Model | Cards | Context | Load s | Decode short | Prefill first / last depth | Decode first / last depth "
           "| First token at last depth | Recall | Record |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, d in sorted(records, key=lambda x: (x[1].get("model", ""), len(x[1].get("cards", [])), x[0])):
        probes = d.get("depth_probes") or ([d["long_probe"]] if d.get("long_probe") else [])
        first, last = (probes[0], probes[-1]) if probes else ({}, {})
        recall = [p.get("recall_ok") for p in probes]
        recall_s = ("ok" if all(recall) else f"{recall.count(False)} of {len(recall)} failed") if recall else "-"
        if probes and not any(recall) and not any("recall_in" in p for p in probes):
            recall_s = "not measured"  # thinking model, before reasoning text was checked
        ctx = (d.get("load") or {}).get("ctx_allocated") or (d.get("plan") or {}).get("ctx")
        fixed = "fixed" if "fixed" in str((d.get("methodology") or {}).get("plan", "")) else (d.get("plan") or {}).get("ctx_limit", "")
        out.append("| {} | {} | {} ({}) | {} | {} | {} / {} | {} / {} | {} | {} | `{}` |".format(
            d.get("model"), cards(d.get("cards")), f"{int(ctx):,}" if ctx else "-", fixed or "-",
            num((d.get("load") or {}).get("seconds"), "{:.0f}"),
            num((d.get("short_probe") or {}).get("generation_tokens_per_second")),
            num(first.get("prompt_tokens_per_second"), "{:.0f}"), num(last.get("prompt_tokens_per_second"), "{:.0f}"),
            num(first.get("generation_tokens_per_second")), num(last.get("generation_tokens_per_second")),
            f"{float(last['time_to_first_token_seconds']) / 60:.1f} min" if last.get("time_to_first_token_seconds") else "-",
            recall_s, name))
    return out


def characterization_rows(records: list[tuple[str, dict]]) -> list[str]:
    out = ["| Model | Date | Cards | Context | Load s | Decode tok/s | Prompt tok/s | Avg GPU W | Record |",
           "|---|---|---|---|---|---|---|---|---|"]
    for name, d in sorted(records, key=lambda x: (x[1].get("model", ""), x[1].get("recorded_at", ""))):
        rt, dec = d.get("runtime") or {}, d.get("decode") or {}
        gpus = [g.get("gpu") for g in d.get("gpu_envelope") or []]
        out.append("| {} | {} | {} | {} | {} | {} | {} | {} | `{}` |".format(
            d.get("model"), str(d.get("recorded_at", ""))[:10], cards(gpus), rt.get("ctx_size", "-"),
            num((d.get("first_load") or {}).get("seconds"), "{:.0f}"), num(dec.get("generation_tokens_per_second")),
            num(dec.get("prompt_tokens_per_second")), num(d.get("combined_avg_gpu_power_w"), "{:.0f}"), name))
    return out


def split_rows(records: list[tuple[str, dict]]) -> list[str]:
    out = ["| Study | Model | Context | GPUs | Hops | Extra args | Decode tok/s | Prefill tok/s | Load s |",
           "|---|---|---|---|---|---|---|---|---|"]
    for name, d in sorted(records):
        for r in d.get("rows", []):
            out.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                d.get("label"), d.get("model"), d.get("ctx"), ",".join(str(g) for g in r.get("gpus", [])),
                r.get("hops", "-"), r.get("extra_args") or "-", num(r.get("decode_tps")), num(r.get("prefill_tps")),
                r.get("load_s", "-")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--records", default=str(RX))
    ap.add_argument("--output", default=str(OUT))
    a = ap.parse_args()
    by_kind: dict[str, list[tuple[str, dict]]] = {}
    for f in sorted(Path(a.records).glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        kind = d.get("kind") or ("split_scaling" if "rows" in d and "label" in d else "other")
        by_kind.setdefault(kind, []).append((f.name, d))

    lines = ["# Runtime reference", "",
             "Generated by `scripts/active/build_runtime_reference.py` from `results/runtime_experiments/` "
             f"({sum(len(v) for v in by_kind.values())} records, {datetime.now():%Y-%m-%d}). Do not edit; what the "
             "numbers mean and which tool produces each is in [RIG_PERFORMANCE.md](../RIG_PERFORMANCE.md). "
             "Cards: 3090 is GPU 0, 1060 #N is GPU N.", ""]
    if by_kind.get("capacity"):
        lines += ["## Capacity runs", "",
                  "`scripts/integration/capacity_run.py`: loaded at the largest context on the cards (or a fixed one), "
                  "short probe, then depth probes (prefill and decode at each depth, prompt cache off). Depths are "
                  "10-90% of the context; first and last are shown.", ""] + capacity_rows(by_kind.pop("capacity")) + [""]
    if by_kind.get("runtime_characterization"):
        lines += ["## Runtime characterizations", "",
                  "Phase 3.5 (`scripts/integration/runtime_char.py`): sustained decode of a short prompt with GPU "
                  "sampling, at the lane's load.", ""] + characterization_rows(by_kind.pop("runtime_characterization")) + [""]
    if by_kind.get("split_scaling"):
        lines += ["## Split scaling", "", "llm-gateway `tools/split_sweep.py`: the same model on 1 to 5 cards "
                  "(decode median of 3 x 256 tokens, prefill median of 3 prompts).", ""] + split_rows(by_kind.pop("split_scaling")) + [""]
    if by_kind:
        lines += ["## Other records", "", "| Kind | Record | Purpose |", "|---|---|---|"]
        for kind, recs in sorted(by_kind.items()):
            for name, d in recs:
                lines.append(f"| {kind} | `{name}` | {str(d.get('purpose', '')).strip()[:160]} |")
        lines.append("")
    Path(a.output).write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
