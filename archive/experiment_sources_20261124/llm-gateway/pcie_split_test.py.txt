"""PCIe traffic test against a split model: long unique prompts (prefill) plus decode, for a fixed time.

Usage: pcie_split_test.py PORT [SECONDS] [WORKERS]
"""
import json, random, sys, threading, time, urllib.request

PORT = int(sys.argv[1])
DURATION_S = int(sys.argv[2]) if len(sys.argv) > 2 else 600
WORKERS = int(sys.argv[3]) if len(sys.argv) > 3 else 3
URL = f"http://127.0.0.1:{PORT}/v1/chat/completions"

FILLER = ("The rig logs temperature, fan speed, power draw and clock for every card each half second. "
          "Operators compare runs by card identity so moving boards between slots keeps history intact. ")

stats = {"prefill": [], "decode": [], "prompt_tok": 0, "gen_tok": 0, "errors": 0, "requests": 0}
lock = threading.Lock()
stop_at = time.time() + DURATION_S


def one(long_prompt: bool) -> None:
    tag = f"Run id {random.randint(0, 10**9)}.\n"
    if long_prompt:
        body = tag + FILLER * random.randint(180, 260) + "\nSummarize the above in three sentences."
        max_tokens = 128
    else:
        body = tag + "Write a detailed technical explanation of PCIe link training and error recovery."
        max_tokens = 512
    req = urllib.request.Request(URL, data=json.dumps({
        "model": "x", "messages": [{"role": "user", "content": body}],
        "max_tokens": max_tokens, "temperature": 0.7}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            d = json.loads(r.read())
        t = d.get("timings", {})
        with lock:
            stats["requests"] += 1
            stats["prompt_tok"] += t.get("prompt_n", 0)
            stats["gen_tok"] += t.get("predicted_n", 0)
            if t.get("prompt_n", 0) > 500:
                stats["prefill"].append(t.get("prompt_per_second", 0))
            stats["decode"].append(t.get("predicted_per_second", 0))
    except Exception as e:
        with lock:
            stats["errors"] += 1
        print(f"{time.strftime('%H:%M:%S')} error: {e}", flush=True)


def worker(i: int) -> None:
    n = 0
    while time.time() < stop_at:
        one(long_prompt=(n % 3 != 2))
        n += 1


def avg(xs):
    return sum(xs) / len(xs) if xs else 0


threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(WORKERS)]
print(f"{time.strftime('%H:%M:%S')} start: port {PORT}, {DURATION_S} s, {WORKERS} workers", flush=True)
for t in threads:
    t.start()
while any(t.is_alive() for t in threads):
    time.sleep(60)
    with lock:
        print(f"{time.strftime('%H:%M:%S')} requests {stats['requests']} errors {stats['errors']} "
              f"prompt tok {stats['prompt_tok']} gen tok {stats['gen_tok']} "
              f"prefill avg {avg(stats['prefill']):.0f} tok/s decode avg {avg(stats['decode']):.1f} tok/s",
              flush=True)
print(json.dumps({k: (round(avg(v), 1) if isinstance(v, list) else v) for k, v in stats.items()}), flush=True)
