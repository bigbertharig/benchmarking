#!/usr/bin/env python3
"""Extract canonical result rows from one lm-eval reasoning task output."""

from __future__ import annotations

import argparse
import json
import re
import string
from pathlib import Path
from typing import Any


# Flexible scoring: a correct answer counts even when the model did not use the answer
# phrasing the harness extracts. Only for tasks whose prompt demonstrates a format
# without instructing it (BBH few-shot examples, DROP plain questions). Tasks that
# instruct a format (IFEval) stay strict. Strict rows are emitted unchanged beside these.
ANSWER_PHRASE = re.compile(r"(?i)\b(?:final\s+)?answer(?:\s+is\s*:?|\s*:)\s*(.+)")
OPTION_TOKEN = re.compile(r"\(([A-Ra-r])\)")
LEAD_IN = re.compile(r"(?i)^\s*(?:so\s+)?(?:the\s+)?(?:final\s+)?answer(?:\s+is)?\s*[:\-]?\s*")
OPTION = re.compile(r"^\(([a-z])\)$")


def _response(sample: dict[str, Any]) -> str:
    resps = sample.get("resps") or [[""]]
    first = resps[0]
    return str(first[0] if isinstance(first, list) and first else first or "")


def _clean(text: str) -> str:
    text = text.strip().strip("*`'\" ").rstrip(".").strip().strip("*`'\" ")
    return re.sub(r"\s+", " ", text).lower()


def _bbh_candidates(response: str) -> list[str]:
    candidates = [m.group(1).split("\n")[0] for m in ANSWER_PHRASE.finditer(response)][-1:]
    stripped = response.strip()
    try:
        parsed = json.loads(stripped)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        for key in ("answer", "final_answer", "result"):
            if key in parsed:
                candidates.append(str(parsed[key]))
    lines = [line for line in stripped.splitlines() if line.strip()]
    if lines:
        candidates.append(lines[-1])
        # A concluding line that names exactly one option ("Therefore, the sarcastic
        # statement is (A).") answers with that option.
        options = {o.lower() for o in OPTION_TOKEN.findall(lines[-1])}
        if len(options) == 1:
            candidates.append(f"({options.pop()})")
    candidates.append(stripped)
    return [_clean(c) for c in candidates if c and len(c.strip()) <= 80]


def _bbh_matches(candidate: str, target: str) -> bool:
    if candidate == target:
        return True
    option = OPTION.match(target)
    if option:
        letter = option.group(1)
        return candidate in (letter, f"{letter})") or candidate.startswith(f"({letter}) ")
    return False


def bbh_flexible(samples: list[dict[str, Any]]) -> tuple[float, int] | None:
    """Fraction correct under flexible extraction, and how many strict misses it rescued."""
    if not samples:
        return None
    correct = rescued = 0
    for sample in samples:
        target = _clean(str(sample.get("target", "")))
        strict = bool(sample.get("exact_match"))
        ok = strict or any(_bbh_matches(c, target) for c in _bbh_candidates(_response(sample)))
        correct += ok
        rescued += ok and not strict
    return correct / len(samples), rescued


NUMBER_WORDS = {
    word: str(float(value))
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}


def _drop_tokens(text: str) -> list[str]:
    text = LEAD_IN.sub("", text.lower())
    text = "".join(" " if ch in string.punctuation and ch not in ".-" else ch for ch in text)
    tokens = []
    for token in text.split():
        token = token.strip(".-")
        if token in ("a", "an", "the") or not token:
            continue
        if token in NUMBER_WORDS:
            tokens.append(NUMBER_WORDS[token])
            continue
        try:
            token = str(float(token.replace(",", "")))
        except ValueError:
            pass
        tokens.append(token)
    return tokens


def _contains(haystack: list[str], needle: list[str]) -> bool:
    if not needle:
        return False
    n = len(needle)
    return any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def drop_flexible(samples: list[dict[str, Any]]) -> tuple[float, int] | None:
    """A response passes when every span of some gold answer appears in it.

    Extra context around the answer ("Janikowski scored 2 field goals (33-yard and
    30-yard)") is accepted; the strict EM row still records exact phrasing.
    """
    if not samples:
        return None
    correct = rescued = 0
    for sample in samples:
        response = _drop_tokens(_response(sample))
        golds = (sample.get("doc") or {}).get("answers") or []
        strict = bool(sample.get("em"))
        ok = strict or any(
            spans and all(_contains(response, _drop_tokens(str(span))) for span in spans)
            for spans in golds
        )
        correct += ok
        rescued += ok and not strict
    return correct / len(samples), rescued


def _count(block: Any) -> int | None:
    if isinstance(block, dict):
        value = block.get("effective") or block.get("original")
    elif isinstance(block, (int, float)):
        value = block
    else:
        return None
    if value is None or int(value) <= 0:
        return None
    return int(value)


def sample_count_for(task: str, data: dict[str, Any]) -> int:
    samples = data.get("n-samples") or {}
    direct = _count(samples.get(task))
    if direct is not None:
        return direct

    child_counts = [
        count
        for name, block in samples.items()
        if str(name).startswith(f"{task}_")
        if (count := _count(block)) is not None
    ]
    if child_counts:
        return sum(child_counts)
    raise ValueError(f"missing sample count for {task}")


def extract_rows(
    task: str, data: dict[str, Any], samples: list[dict[str, Any]] | None = None
) -> list[tuple[Any, ...]]:
    results = data.get("results", {})
    groups = data.get("groups", {})
    sample_count = sample_count_for(task, data)
    rows: list[tuple[Any, ...]] = []

    def emit(
        test_id: str,
        score: Any,
        metric: str,
        raw: Any = None,
        normalized: Any = None,
        compatibility: str = "unknown",
        extractor_failures: int = 0,
        notes: str = "",
    ) -> None:
        if score is None:
            return
        raw = score if raw is None else raw
        normalized = score if normalized is None else normalized
        rows.append(
            (
                test_id,
                score,
                metric,
                raw,
                normalized,
                compatibility,
                extractor_failures,
                sample_count,
                notes,
            )
        )

    if task == "gsm8k":
        block = results.get("gsm8k", {})
        strict = block.get("exact_match,strict-match")
        flexible = block.get("exact_match,flexible-extract")
        failures = round(max(0.0, float(flexible or 0) - float(strict or 0)) * sample_count)
        compatibility = "degraded" if failures else "compatible"
        emit("gsm8k_strict", strict, "exact_match,strict-match", strict, flexible, compatibility, failures)
        emit("gsm8k_flexible", flexible, "exact_match,flexible-extract", strict, flexible, compatibility, failures)
    elif task == "bbh":
        block = groups.get("bbh") or results.get("bbh", {})
        strict = block.get("exact_match,get-answer")
        emit("bbh", strict, "exact_match,get-answer")
        flexible = bbh_flexible(samples or [])
        if flexible is not None and strict is not None:
            score, rescued = flexible
            emit("bbh_flexible", score, "exact_match,flexible-extract", strict, score,
                 "degraded" if rescued else "compatible", rescued)
    elif task == "drop":
        block = results.get("drop", {})
        strict = block.get("em,none")
        emit("drop_em", strict, "em,none")
        emit("drop_f1", block.get("f1,none"), "f1,none")
        flexible = drop_flexible(samples or [])
        if flexible is not None and strict is not None:
            score, rescued = flexible
            emit("drop_flexible", score, "answer_contained", strict, score,
                 "degraded" if rescued else "compatible", rescued)
    else:
        block = groups.get(task) or results.get(task, {})
        for key, value in block.items():
            metric_name = key.split(",", 1)[0]
            if key == "alias" or metric_name.endswith("_stderr"):
                continue
            if isinstance(value, (int, float)):
                emit(f"{task}_{key.replace(',', '_')}", value, key)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("task_output_dir")
    args = parser.parse_args()

    files = sorted(Path(args.task_output_dir).glob("**/results_*.json"))
    if not files:
        return 0
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    # Per-sample responses (lm-eval --log_samples) written by the same run as the results file.
    run_stamp = files[-1].stem.removeprefix("results_")
    samples = [
        json.loads(line)
        for path in sorted(files[-1].parent.glob(f"samples_*_{run_stamp}.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    try:
        rows = extract_rows(args.task, data, samples)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    for row in rows:
        print("\t".join(str(value) for value in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
