"""NEW_MODEL_INTEGRATION Phase 3 litmus: reasoning (555), JSON, code. No system prompt, temperature 0."""
import json, sys, urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "11434"

def chat(content):
    body = {"messages": [{"role": "user", "content": content}], "temperature": 0}
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions",
                                 json.dumps(body).encode(), {"Content-Type": "application/json"})
    msg = json.load(urllib.request.urlopen(req, timeout=300))["choices"][0]["message"]
    return msg.get("content") or "", msg.get("reasoning_content") or ""

checks = []
c, r = chat("What is 15 * 37? Reply with ONLY the number.")
checks.append(("reasoning", "555" in c and "<think>" not in c, c, r))
c, r = chat('Return a JSON object with keys "name" and "age" for a 30-year-old named Alice. Output ONLY valid JSON, no explanation.')
try:
    ok = isinstance(json.loads(c), dict)
except Exception:
    ok = False
checks.append(("json", ok, c, r))
c, r = chat("Write a Python function is_palindrome(s) that returns True if s is a palindrome. Output ONLY the function, no explanation.")
checks.append(("code", "def is_palindrome" in c and "<think>" not in c, c, r))
for name, ok, c, r in checks:
    print(f"{name:9} {'PASS' if ok else 'FAIL'}  content={c[:160]!r}  reasoning_content={len(r)} chars")
