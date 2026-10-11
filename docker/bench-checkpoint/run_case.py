"""bench-checkpoint prototype runner: one real repo case, one model, one run.

Creates a throwaway git worktree at the case's base commit, gives the model a
bounded set of repo tools through an OpenAI-compatible endpoint (streaming, so
time-to-first-token and generation speed are measured), then grades by adding
the accepted commit's hidden tests and running the grader targets.

Usage (from this folder):
  python run_case.py --case cases/CKPT-SEC-001.json --model openai/gpt-5.4
  python run_case.py --case ... --model chat-27b --base-url http://127.0.0.1:8080/v1 --no-key

Local repo paths come from repos.local.json (gitignored); see repos.example.json.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BASE = "https://openrouter.ai/api/v1"
READ_LIMIT = 400          # max lines returned per read_file call
OUTPUT_LIMIT = 6000       # max chars of tool output returned to the model
SEARCH_LIMIT = 80         # max matching lines per search

SYSTEM = """You are a coding agent working in a git repository on a real task.
Use the tools to explore the code, make focused edits, and run tests.
Paths are relative to the repository root. Read before you edit.
Prefer small, targeted changes that match the surrounding code.
When the task is complete, reply with a short summary and the word DONE.
Do not ask the user questions; make reasonable decisions and proceed."""

TOOLS = [
    {"type": "function", "function": {
        "name": "list_dir", "description": "List files and folders in a directory (non-recursive).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": f"Read a file. Returns at most {READ_LIMIT} lines; use start_line to page.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "start_line": {"type": "integer"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "search",
        "description": "Search tracked files for a regular expression (git grep). Optional path limits the search.",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "replace_in_file",
        "description": "Replace exactly one occurrence of old_text with new_text in a file.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
            "required": ["path", "old_text", "new_text"]}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Create or overwrite a file with the given content.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "run_tests",
        "description": "Run pytest on one or more test paths under tests/ (for example tests/test_x.py).",
        "parameters": {"type": "object", "properties": {
            "paths": {"type": "array", "items": {"type": "string"}}}, "required": ["paths"]}}},
]


def load_key(env_file):
    p = Path(env_file)
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY=") and line.split("=", 1)[1].strip():
                return line.split("=", 1)[1].strip()
    return os.environ.get("OPENROUTER_API_KEY")


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:400])
    return r.stdout


class Repo:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.edited = set()

    def path(self, rel):
        p = (self.root / (rel or ".")).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError("path escapes repository")
        if ".git" in p.relative_to(self.root).parts:
            raise ValueError("access to .git is not allowed")
        return p

    def tool(self, name, a):
        try:
            if name == "list_dir":
                p = self.path(a.get("path", "."))
                items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                return "\n".join(x.name + ("/" if x.is_dir() else "") for x in items
                                 if x.name not in (".git", "__pycache__", "node_modules"))
            if name == "read_file":
                lines = self.path(a["path"]).read_text(encoding="utf-8", errors="replace").splitlines()
                start = max(1, int(a.get("start_line") or 1))
                chunk = lines[start - 1:start - 1 + READ_LIMIT]
                body = "\n".join(f"{i}: {l}" for i, l in enumerate(chunk, start))
                more = f"\n... ({len(lines)} lines total; continue with start_line={start + READ_LIMIT})" \
                    if start - 1 + READ_LIMIT < len(lines) else ""
                return body + more
            if name == "search":
                args = ["grep", "-n", "-I", "-E", a["pattern"]]
                if a.get("path"):
                    args += ["--", a["path"]]
                out = git(self.root, *args, check=False).splitlines()
                return "\n".join(out[:SEARCH_LIMIT]) + (f"\n... {len(out)} matches total" if len(out) > SEARCH_LIMIT else "") or "no matches"
            if name == "replace_in_file":
                p = self.path(a["path"])
                text = p.read_text(encoding="utf-8")
                n = text.count(a["old_text"])
                if n != 1:
                    return f"error: old_text found {n} times; it must match exactly once"
                p.write_text(text.replace(a["old_text"], a["new_text"], 1), encoding="utf-8", newline="")
                self.edited.add(a["path"].replace("\\", "/"))
                return "ok"
            if name == "write_file":
                p = self.path(a["path"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(a["content"], encoding="utf-8", newline="")
                self.edited.add(a["path"].replace("\\", "/"))
                return "ok"
            if name == "run_tests":
                paths = [x for x in a.get("paths") or [] if x.replace("\\", "/").startswith("tests/")]
                if not paths:
                    return "error: give one or more paths under tests/"
                ok, out = pytest(self.root, paths)
                return ("PASSED\n" if ok else "FAILED\n") + out[-OUTPUT_LIMIT:]
            return f"error: unknown tool {name}"
        except Exception as e:
            return f"error: {type(e).__name__}: {e}"


def pytest(root, paths, timeout=300):
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *paths],
                       cwd=root, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return r.returncode == 0, (r.stdout + r.stderr)


def stream_chat(base_url, key, model, messages, max_tokens):
    """Stream one completion; return (message, usage, timing)."""
    body = {"model": model, "messages": messages, "tools": TOOLS, "max_tokens": max_tokens,
            "stream": True, "stream_options": {"include_usage": True}, "usage": {"include": True}}
    headers = {"Content-Type": "application/json", "X-Title": "bench-checkpoint"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                 json.dumps(body).encode(), headers)
    t0 = time.time()
    first = None
    content, calls, usage = [], {}, {}
    with urllib.request.urlopen(req, timeout=600) as r:
        for raw in r:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                ev = json.loads(data)
            except ValueError:
                continue
            if ev.get("usage"):
                usage = ev["usage"]
            for ch in ev.get("choices") or []:
                d = ch.get("delta") or {}
                if (d.get("content") or d.get("tool_calls") or d.get("reasoning")) and first is None:
                    first = time.time()
                if d.get("content"):
                    content.append(d["content"])
                for tc in d.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": []})
                    slot["id"] = tc.get("id") or slot["id"]
                    fn = tc.get("function") or {}
                    slot["name"] = fn.get("name") or slot["name"]
                    if fn.get("arguments"):
                        slot["args"].append(fn["arguments"])
    t1 = time.time()
    msg = {"role": "assistant", "content": "".join(content) or None}
    if calls:
        msg["tool_calls"] = [{"id": c["id"] or f"call_{i}", "type": "function",
                              "function": {"name": c["name"], "arguments": "".join(c["args"]) or "{}"}}
                             for i, c in sorted(calls.items())]
    gen_s = (t1 - first) if first else 0.0
    timing = {"ttft_s": round((first or t1) - t0, 2), "gen_s": round(gen_s, 2), "total_s": round(t1 - t0, 2)}
    return msg, usage, timing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--env-file", default=str(HERE / ".env"))
    ap.add_argument("--no-key", action="store_true", help="local endpoints that need no key")
    ap.add_argument("--repos", default=str(HERE / "repos.local.json"))
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--keep-worktree", action="store_true")
    a = ap.parse_args()

    case = json.loads(Path(a.case).read_text(encoding="utf-8"))
    repos = json.loads(Path(a.repos).read_text(encoding="utf-8"))
    src = Path(repos[case["repo"]])
    key = None if a.no_key else load_key(a.env_file)
    if not a.no_key and not key:
        raise SystemExit("No OPENROUTER_API_KEY (copy .env.example to .env)")
    budget = case.get("budget", {})
    max_turns, max_cost = budget.get("max_turns", 40), budget.get("max_cost_usd", 2.0)
    time_limit = budget.get("time_s", 1800)

    wt = Path(tempfile.mkdtemp(prefix=f"ckpt_{case['case_id']}_")) / "repo"
    git(src, "worktree", "add", "--detach", str(wt), case["base_commit"])
    repo = Repo(wt)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": case["request"]}]
    turns, totals = [], {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
    peak_ctx, stop, final, error = 0, "max_turns", "", None
    retries = []
    t_start = time.time()
    try:
        for n in range(1, max_turns + 1):
            for attempt in range(1, 4):  # transient provider/network errors are retried
                try:
                    msg, usage, timing = stream_chat(a.base_url, key, a.model, messages, a.max_tokens)
                    break
                except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                    if isinstance(e, urllib.error.HTTPError) and e.code < 500 and e.code != 429:
                        raise
                    retries.append({"turn": n, "attempt": attempt, "error": str(e)[:160]})
                    print(f"  turn {n:2}: transient error, retry {attempt}: {str(e)[:80]}", flush=True)
                    if attempt == 3:
                        raise
                    time.sleep(5 * attempt)
            pt, ct = usage.get("prompt_tokens", 0) or 0, usage.get("completion_tokens", 0) or 0
            totals["prompt_tokens"] += pt
            totals["completion_tokens"] += ct
            totals["cost"] += float(usage.get("cost", 0) or 0)
            peak_ctx = max(peak_ctx, pt)
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
            turns.append({"turn": n, **timing, "prompt_tokens": pt, "completion_tokens": ct,
                          "cached_tokens": cached,
                          "tok_s": round(ct / timing["gen_s"], 1) if timing["gen_s"] > 0 and ct else None,
                          "tools": [c["function"]["name"] for c in msg.get("tool_calls", [])]})
            print(f"  turn {n:2}: ttft {timing['ttft_s']:5.1f}s  ctx {pt:6}  out {ct:5}  "
                  f"tools {turns[-1]['tools']}", flush=True)
            messages.append(msg)
            if not msg.get("tool_calls"):
                final, stop = (msg.get("content") or "").strip(), "finished"
                break
            for c in msg["tool_calls"]:
                try:
                    args = json.loads(c["function"]["arguments"] or "{}")
                except ValueError:
                    args = {}
                out = repo.tool(c["function"]["name"], args)
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": out[:OUTPUT_LIMIT]})
            if totals["cost"] >= max_cost:
                stop = "cost_limit"
                break
            if time.time() - t_start >= time_limit:
                stop = "time_limit"
                break
    except urllib.error.HTTPError as e:
        error, stop = f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}", "error"
    except Exception as e:
        error, stop = f"{type(e).__name__}: {e}", "error"

    # Grade: drop in the accepted commit's hidden tests, run the grader targets.
    diff = git(wt, "diff", "--stat", check=False)
    for t in case.get("hidden_tests", []):
        content = git(src, "show", f"{case['accepted_commit']}:{t}")
        p = wt / t
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="")
    passed, grade_out = pytest(wt, case["grader"]["targets"])
    gen_rates = [t["tok_s"] for t in turns if t["tok_s"]]
    result = {
        "case_id": case["case_id"], "model": a.model, "base_url": a.base_url,
        "grader_pass": passed, "stop": stop, "error": error, "turns": len(turns),
        "wall_s": round(time.time() - t_start, 1), **totals, "cost": round(totals["cost"], 4),
        "peak_context_tokens": peak_ctx,
        "median_ttft_s": sorted(t["ttft_s"] for t in turns)[len(turns) // 2] if turns else None,
        "median_gen_tok_s": sorted(gen_rates)[len(gen_rates) // 2] if gen_rates else None,
        "edited_files": sorted(repo.edited),
        "edited_outside_footprint": sorted(set(repo.edited) - set(case["accepted_footprint"]["files"])
                                           - {t for t in repo.edited if t.startswith("tests/")}),
        "diff_stat": diff.strip().splitlines()[-1:] if diff.strip() else [],
        "grade_tail": grade_out.strip().splitlines()[-1:] if grade_out.strip() else [],
        "final": final[:300], "retries": retries, "turn_log": turns,
    }
    outdir = HERE / "results"
    outdir.mkdir(exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", a.model)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (outdir / f"{case['case_id']}__{safe}__{stamp}.json").write_text(json.dumps(result, indent=2))
    if not a.keep_worktree:
        git(src, "worktree", "remove", "--force", str(wt), check=False)
        shutil.rmtree(wt.parent, ignore_errors=True)
        git(src, "worktree", "prune", check=False)
    summary = {k: result[k] for k in ("case_id", "model", "grader_pass", "stop", "turns", "wall_s",
                                      "cost", "peak_context_tokens", "median_ttft_s",
                                      "median_gen_tok_s", "edited_files", "grade_tail", "error")}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
