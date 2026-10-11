"""Smoke test for a bench-checkpoint style harness against an OpenAI-compatible API.

Builds a tiny repo with a known bug and a unittest suite, gives the model a
bounded tool loop (list/read/replace/write files, run tests), then grades by
running the tests. Records turns, tokens, cost, and wall time per model.

Usage (from this folder, after copying .env.example to .env and adding the key):
  python ckpt_smoke.py --models openai/gpt-5.4 anthropic/claude-opus-4.6
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_TURNS = 12
TIMEOUT_S = 180

REPO_FILES = {
    "geo/ranges.py": '''"""Year range helpers used by pack time filters."""


def parse_range(text):
    """Parse 'YYYY-YYYY' or a single 'YYYY' into an inclusive (start, end) tuple."""
    text = text.strip()
    if "-" in text:
        start, end = text.split("-")
        return int(start), int(end)
    year = int(text)
    return year, year


def years_in_range(text):
    """Return the list of years covered by a range string, inclusive."""
    start, end = parse_range(text)
    return list(range(start, end))


def overlaps(a, b):
    """True if two range strings share at least one year."""
    a0, a1 = parse_range(a)
    b0, b1 = parse_range(b)
    return a0 < b1 and b0 < a1
''',
    "geo/__init__.py": "",
    "tests/__init__.py": "",
    "tests/test_ranges.py": '''import unittest

from geo.ranges import overlaps, parse_range, years_in_range


class RangeTests(unittest.TestCase):
    def test_parse_single(self):
        self.assertEqual(parse_range("2011"), (2011, 2011))

    def test_parse_span_with_spaces(self):
        self.assertEqual(parse_range(" 2010 - 2012 "), (2010, 2012))

    def test_years_inclusive(self):
        self.assertEqual(years_in_range("2010-2012"), [2010, 2011, 2012])

    def test_single_year_list(self):
        self.assertEqual(years_in_range("2015"), [2015])

    def test_overlap_shared_edge_year(self):
        self.assertTrue(overlaps("2000-2010", "2010-2020"))

    def test_no_overlap(self):
        self.assertFalse(overlaps("2000-2004", "2005-2009"))


if __name__ == "__main__":
    unittest.main()
''',
}

REQUEST = (
    "Users report that year filters drop the last year of a range, and that two "
    "ranges sharing a boundary year are treated as not overlapping. Fix the bugs "
    "in geo/ranges.py so the test suite passes. Do not edit the tests. Run the "
    "tests to confirm, then reply DONE with a one-line summary."
)

SYSTEM = (
    "You are a coding agent working in a small repository. Use the provided tools "
    "to inspect files, make minimal edits, and run the tests. Paths are relative "
    "to the repository root. Stop when the tests pass."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "list_files", "description": "List all files in the repository.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "replace_in_file",
        "description": "Replace exactly one occurrence of old_text with new_text in a file.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "old_text": {"type": "string"},
            "new_text": {"type": "string"}},
            "required": ["path", "old_text", "new_text"]}}},
    {"type": "function", "function": {
        "name": "run_tests", "description": "Run the unittest suite and return the output.",
        "parameters": {"type": "object", "properties": {}}}},
]


def load_key(env_file):
    p = Path(env_file)
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    raise SystemExit(f"No OPENROUTER_API_KEY in {p} or the environment. "
                     "Copy .env.example to .env and fill it in.")


def make_repo():
    root = Path(tempfile.mkdtemp(prefix="ckpt_case_"))
    for rel, text in REPO_FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    return root


def safe_path(root, rel):
    p = (root / rel).resolve()
    if root.resolve() not in p.parents and p != root.resolve():
        raise ValueError("path escapes repository")
    return p


def run_tests(root):
    r = subprocess.run([sys.executable, "-I", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                       cwd=root, capture_output=True, text=True, timeout=60)
    return r.returncode == 0, (r.stdout + r.stderr)[-3000:]


def call_tool(root, name, args, state):
    try:
        if name == "list_files":
            return "\n".join(str(p.relative_to(root)).replace("\\", "/")
                             for p in sorted(root.rglob("*")) if p.is_file()
                             and "__pycache__" not in p.parts)
        if name == "read_file":
            return safe_path(root, args["path"]).read_text(encoding="utf-8")
        if name == "replace_in_file":
            rel = args["path"].replace("\\", "/")
            if rel.startswith("tests/"):
                state["edited_tests"] = True
            p = safe_path(root, rel)
            text = p.read_text(encoding="utf-8")
            n = text.count(args["old_text"])
            if n != 1:
                return f"error: old_text found {n} times; it must match exactly once"
            p.write_text(text.replace(args["old_text"], args["new_text"], 1),
                         encoding="utf-8", newline="\n")
            state["edits"] += 1
            return "ok"
        if name == "run_tests":
            ok, out = run_tests(root)
            return ("PASSED\n" if ok else "FAILED\n") + out
        return f"error: unknown tool {name}"
    except Exception as e:  # tool errors are observations, not crashes
        return f"error: {e}"


def chat(key, model, messages):
    body = json.dumps({"model": model, "messages": messages, "tools": TOOLS,
                       "max_tokens": 2000, "usage": {"include": True}}).encode()
    req = urllib.request.Request(BASE_URL, body, {
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "X-Title": "bench-checkpoint-smoke"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.load(r)


def run_case(key, model):
    root = make_repo()
    state = {"edits": 0, "edited_tests": False}
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": REQUEST}]
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
    t0 = time.time()
    turns, error, final = 0, None, ""
    try:
        for turns in range(1, MAX_TURNS + 1):
            resp = chat(key, model, messages)
            u = resp.get("usage") or {}
            totals["prompt_tokens"] += u.get("prompt_tokens", 0) or 0
            totals["completion_tokens"] += u.get("completion_tokens", 0) or 0
            totals["cost"] += float(u.get("cost", 0) or 0)
            msg = resp["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            messages.append({k: v for k, v in msg.items()
                             if k in ("role", "content", "tool_calls") and v is not None})
            if not calls:
                final = (msg.get("content") or "").strip()
                break
            for c in calls:
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                out = call_tool(root, c["function"]["name"], args, state)
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": out})
    except urllib.error.HTTPError as e:
        error = f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    passed, _ = run_tests(root)
    shutil.rmtree(root, ignore_errors=True)
    return {"model": model, "grader_pass": passed and not state["edited_tests"],
            "edited_tests": state["edited_tests"], "edits": state["edits"], "turns": turns,
            "wall_s": round(time.time() - t0, 1), **totals,
            "cost": round(totals["cost"], 5), "final": final[:160], "error": error}


def main():
    ap = argparse.ArgumentParser()
    here = Path(__file__).resolve().parent
    ap.add_argument("--env-file", default=str(here / ".env"))
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--out", default=str(here / "results" / "ckpt_smoke_results.jsonl"))
    a = ap.parse_args()
    key = load_key(a.env_file)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "a", encoding="utf-8") as fh:
        for m in a.models:
            r = run_case(key, m)
            fh.write(json.dumps(r) + "\n")
            print(json.dumps(r))


if __name__ == "__main__":
    main()
