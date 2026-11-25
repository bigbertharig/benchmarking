#!/usr/bin/env python3
"""rig_stress: power and thermal stress test of the rig, run from the controller. Standard library only.

    python3 tools/rig_stress.py                       the 2026-10-18 test: one model per card, ramp, hold
    python3 tools/rig_stress.py --uncap --spikes      cards at factory limits until the next boot; reload spikes
    python3 tools/rig_stress.py --compare ~/rig_stress/20261018_baseline/summary.json
    python3 tools/rig_stress.py --summarize DIR       (re)write DIR/summary.json from its stream.csv

Everything goes through the harness, so this is also a harness test: one model per card is loaded with
`rigctl load-model` one at a time; generators run on this machine through its tunnel to the rig ports;
if the rig disappears the run records the last readings, waits for it and records what the manager did.

Phases: ramp (one more card every --ramp-s, 3090 first), hold (all cards for --hold-s), optional reload
spikes (one card at a time is unloaded and reloaded while the others stay hammered), then cleanup
(unload, caps restored) unless --keep-loaded; --hammer-after GPU keeps one card at full load at the end
(to find it physically). Stops all load at GPU --abort-gpu-c or CPU --abort-cpu-c.

Telemetry: per GPU every 500 ms from nvidia-smi on the rig (instant power, temperature, fan, SM clock,
throttle reasons) streamed to stream.csv here, so the readings up to a crash survive; CPU package and
reachability from `rigctl status` every 10 s. summary.json has, per card (keyed by GPU UUID, which stays
with the board when cards move between slots): hold-phase temperature, fan, power and clock averages and
maxima, plus the rig's peak and the spike peaks. --compare prints the change against an earlier summary.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RIGCTL = [sys.executable, str(HERE / "rigctl.py")]
RIG = os.getenv("RIG_HOST", "10.0.0.3")
# 2026-10-18 assignment: the 3090 gets the dense 27B (it holds its 450 W limit), each 1060 a small model.
DEFAULT_MODELS = "0=qwen3.6:27b,1=ornith-1.5:9b,2=ministral-3:8b,3=qwen2.5-coder:7b,4=gemma-4:e4b,5=llama3.2:3b"
FALLBACK_SMALL = "llama3.2:3b"   # for a card the assignment does not name (new cards)
UNCAP = {"by_model": {"GTX 1060": {"156": 156, "120": 120}, "RTX 3090 Ti": 450}, "by_index": {}}  # factory limits
PROMPT = ("Write a very long, detailed story about a lighthouse keeper and a storm that lasts a week. "
          "Describe every day in depth, with dialogue, and do not stop or summarize.")
FIELDS = "index,uuid,power.draw.instant,temperature.gpu,fan.speed,clocks.sm,clocks_event_reasons.active"


class Run:
    def __init__(self, a: argparse.Namespace):
        self.a = a
        self.out = Path(a.out or Path.home() / "rig_stress" / time.strftime("%Y%m%d_%H%M%S"))
        self.out.mkdir(parents=True, exist_ok=True)
        self.phase = "setup"
        self.stop_all = threading.Event()
        self.gen_stop: dict[int, threading.Event] = {}
        self.tokens: dict[int, int] = {}
        self.errors: dict[int, int] = {}
        self.cpu_max = 0.0
        self.lost_at: str | None = None
        self.spikes: list[dict] = []
        self.last_rows: dict[int, list] = {}

    # ------------------------------------------------------------------ plumbing

    def log(self, msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        with open(self.out / "events.log", "a") as f:
            f.write(line + "\n")

    def sh(self, cmd: str, timeout: int = 120) -> str:
        p = subprocess.run(["ssh", "-o", "ConnectTimeout=10", RIG, cmd], capture_output=True, text=True,
                           timeout=timeout)
        return (p.stdout + p.stderr).strip()

    def rigctl(self, *args: str, timeout: int = 1000) -> dict:
        p = subprocess.run(RIGCTL + list(args), capture_output=True, text=True, timeout=timeout)
        try:
            return json.loads(p.stdout)
        except ValueError:
            return {"error": {"message": (p.stdout + p.stderr)[-300:]}}

    def limits(self) -> str:
        return self.sh("nvidia-smi --query-gpu=index,power.limit --format=csv,noheader | tr '\\n' ' '")

    # ------------------------------------------------------------------ load and telemetry

    def generate(self, gpu: int) -> None:
        url = f"http://127.0.0.1:{11434 + gpu}/v1/chat/completions"
        body = json.dumps({"model": "x", "messages": [{"role": "user", "content": PROMPT}],
                           "max_tokens": 2048, "temperature": 0.9}).encode()
        while not self.gen_stop[gpu].is_set() and not self.stop_all.is_set():
            try:
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=900) as r:
                    usage = json.loads(r.read()).get("usage") or {}
                    self.tokens[gpu] = self.tokens.get(gpu, 0) + int(usage.get("completion_tokens") or 0)
            except Exception:  # noqa: BLE001 (the rig may vanish mid-request)
                self.errors[gpu] = self.errors.get(gpu, 0) + 1
                time.sleep(2)

    def start_gen(self, gpu: int) -> None:
        self.gen_stop[gpu] = threading.Event()
        threading.Thread(target=self.generate, args=(gpu,), daemon=True).start()

    def stream(self) -> None:
        cmd = ["ssh", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
               RIG, f"nvidia-smi --query-gpu={FIELDS} --format=csv,noheader,nounits -lms 500"]
        with open(self.out / "stream.csv", "a", newline="") as f, \
                subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as p:
            w = csv.writer(f)
            w.writerow(["t", "phase", "gpu", "uuid", "power_w", "temp_c", "fan_pct", "sm_mhz", "throttle"])
            for line in p.stdout:
                parts = [x.strip() for x in line.split(",")]
                if len(parts) != 7 or not parts[0].isdigit():
                    continue
                gpu, temp = int(parts[0]), _num(parts[3])
                row = [f"{time.time():.2f}", self.phase, gpu, parts[1], _num(parts[2]), temp, _num(parts[4]),
                       _num(parts[5]), parts[6]]
                w.writerow(row)
                self.last_rows[gpu] = row
                if temp >= self.a.abort_gpu_c and not self.stop_all.is_set():
                    self.log(f"ABORT: GPU {gpu} at {temp:.0f} C; all load stopped")
                    self.stop_all.set()
                if self.phase == "done":
                    break
                f.flush()
            p.terminate()
        if self.phase != "done":
            self.log("nvidia-smi stream ended (rig gone?)")

    def watch(self) -> None:
        while self.phase != "done":
            s = self.rigctl("status", "--json", timeout=60)
            reach = not s.get("from_copy") and "error" not in s
            cpu = (s.get("guard") or {}).get("cpu_package_c")
            if reach and isinstance(cpu, (int, float)):
                self.cpu_max = max(self.cpu_max, cpu)
                if cpu >= self.a.abort_cpu_c and not self.stop_all.is_set():
                    self.log(f"ABORT: CPU package {cpu:.0f} C; all load stopped")
                    self.stop_all.set()
            if not reach and not self.lost_at:
                self.lost_at = time.strftime("%H:%M:%S")
                last = {g: r[4:8] for g, r in sorted(self.last_rows.items())}
                self.log(f"RIG UNREACHABLE at {self.lost_at} during {self.phase}; last per GPU "
                         f"[power, temp, fan, sm]: {last}")
                self.stop_all.set()
            time.sleep(10)

    def wait(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end and not self.stop_all.is_set():
            time.sleep(min(1.0, end - time.time()))

    def peak_since(self, t0: float) -> float:
        ticks = _ticks([r for r in _read_stream(self.out / "stream.csv") if float(r["t"]) >= t0])
        return max((sum(float(r["power_w"] or 0) for r in tick) for tick in ticks), default=0.0)

    # ------------------------------------------------------------------ the run

    def main(self) -> int:
        a = self.a
        assign = dict(x.split("=", 1) for x in a.models.split(",") if "=" in x)
        st = self.rigctl("status", "--json", timeout=60)
        gpus = sorted(int(g["gpu"]) for g in st.get("gpus") or [])
        if not gpus:
            self.log(f"cannot read the rig: {st.get('error')}")
            return 1
        plan = [(g, assign.get(str(g), FALLBACK_SMALL)) for g in gpus]
        self.log(f"rig stress start; out {self.out}; cards {plan}; uncap={a.uncap} spikes={a.spikes}")
        (self.out / "config.json").write_text(json.dumps({"args": vars(a), "plan": plan}, indent=2))
        if a.uncap:
            self.sh("sudo -n mkdir -p /run/rig && echo '" + json.dumps(UNCAP) + "' | sudo -n tee "
                    "/run/rig/power_override.json >/dev/null && sudo -n systemctl restart rig-power.service")
        self.log("power limits: " + self.limits())
        threading.Thread(target=self.stream, daemon=True).start()
        threading.Thread(target=self.watch, daemon=True).start()
        profiles: dict[int, str] = {}
        try:
            self.phase = "load"
            for g, model in plan:
                out = self.rigctl("load-model", model, "--gpus", str(g), "--use", "benchmark", "--json")
                if out.get("state") != "ready":
                    self.log(f"LOAD FAILED {model} on GPU {g}: {(out.get('error') or {}).get('message', out)}")
                    return 1
                profiles[g] = out["profile"]
                self.log(f"loaded {model} on GPU {g} ctx {out['ctx']}")
            for i, (g, model) in enumerate(plan, 1):
                if self.stop_all.is_set():
                    break
                self.phase = f"ramp{i}"
                self.start_gen(g)
                self.log(f"ramp {i}/{len(plan)}: hammering GPU {g} ({model})")
                self.wait(a.ramp_s)
            if not self.stop_all.is_set():
                self.phase = "hold"
                self.log(f"HOLD: all {len(plan)} cards for {a.hold_s // 60} min")
                end = time.time() + a.hold_s
                while time.time() < end and not self.stop_all.is_set():
                    self.wait(min(60, end - time.time()))
                    self.minute_line()
            if a.spikes and not self.stop_all.is_set():
                for g, model in sorted(plan, key=lambda x: -x[0]):  # small cards first, the 3090 last
                    if self.stop_all.is_set():
                        break
                    self.phase = f"spike{g}"
                    self.gen_stop[g].set()
                    time.sleep(3)
                    self.rigctl("unload", profiles[g], timeout=300)
                    t0 = time.time()
                    out = self.rigctl("load-model", model, "--gpus", str(g), "--use", "benchmark", "--json")
                    if out.get("state") != "ready":
                        self.log(f"RELOAD FAILED GPU {g}: {(out.get('error') or {}).get('message', out)}")
                        break
                    profiles[g] = out["profile"]
                    load_s = time.time() - t0
                    self.start_gen(g)
                    self.wait(60)
                    peak = self.peak_since(t0)
                    self.spikes.append({"gpu": g, "model": model, "load_s": round(load_s), "peak_w": round(peak)})
                    self.log(f"spike GPU {g}: reloaded in {load_s:.0f} s with the others hammered; peak {peak:.0f} W")
        finally:
            for e in self.gen_stop.values():
                e.set()
            if self.lost_at:
                self.wait_for_rig()
            self.phase = "cleanup"
            if a.hammer_after is not None and a.hammer_after in profiles and not self.lost_at:
                self.stop_all.clear()
                self.start_gen(a.hammer_after)
                self.log(f"GPU {a.hammer_after} stays at full load (Ctrl-C or kill this run to stop)")
            if not a.keep_loaded and a.hammer_after is None:
                for pid in profiles.values():
                    self.rigctl("unload", pid, timeout=300)
                self.log("models unloaded")
            if a.uncap and a.hammer_after is None and not a.keep_loaded:
                self.sh("sudo -n rm -f /run/rig/power_override.json && sudo -n systemctl restart rig-power.service")
                self.log("caps restored: " + self.limits())
            summary = summarize(self.out, extra={"spikes": self.spikes, "cpu_max_c": self.cpu_max,
                                                 "lost_at": self.lost_at, "tokens": self.tokens,
                                                 "request_errors": self.errors})
            self.log(f"DONE: rig peak {summary['rig']['peak_w']} W, hold average {summary['rig']['hold_avg_w']} W, "
                     f"CPU max {self.cpu_max:.0f} C; summary {self.out / 'summary.json'}")
            if a.compare:
                print_compare(summary, json.loads(Path(a.compare).read_text()))
        if a.hammer_after is not None and a.hammer_after in profiles:
            while True:
                time.sleep(60)
        self.phase = "done"
        return 0

    def minute_line(self) -> None:
        last = self.last_rows
        total = sum(float(r[4] or 0) for r in last.values())
        hottest = max(last.values(), key=lambda r: float(r[5] or 0), default=None)
        fans = {g: r[6] for g, r in sorted(last.items())}
        self.log(f"hold: {total:.0f} W now; hottest GPU {hottest[2] if hottest else '-'} at "
                 f"{hottest[5] if hottest else '-'} C; fans % {fans}; CPU max {self.cpu_max:.0f} C; "
                 f"tokens {sum(self.tokens.values())}, request errors {sum(self.errors.values())}")

    def wait_for_rig(self) -> None:
        self.log("waiting for the rig to come back (up to 20 min)")
        deadline = time.time() + 1200
        while time.time() < deadline:
            s = self.rigctl("status", "--json", timeout=60)
            if (s.get("rig") or {}).get("reachable") and not s.get("from_copy"):
                time.sleep(40)  # let the reconciler settle the boot hold
                s = self.rigctl("status", "--json", timeout=60)
                ev = [e["event"] for e in (s.get("rig") or {}).get("events", [])][-6:]
                self.log(f"RIG BACK: plan hold {((s.get('plan') or {}).get('hold') or {}).get('reason')}; "
                         f"manager events {ev}; limits {self.limits()}")
                return
            time.sleep(10)
        self.log("rig not back after 20 min")


def _num(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return 0.0


def _read_stream(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("t") != "t"]


def _ticks(rows: list[dict]) -> list[list[dict]]:
    """Group stream rows into sampling ticks: nvidia-smi prints every card once per tick, in index order."""
    ticks: list[list[dict]] = []
    prev = None
    for r in rows:
        g = int(r["gpu"])
        if prev is None or g <= prev:
            ticks.append([])
        ticks[-1].append(r)
        prev = g
    return ticks


def summarize(out: Path, extra: dict | None = None) -> dict:
    """Per card (by UUID) over the hold phase, and the rig's peak, from stream.csv."""
    rows = _read_stream(out / "stream.csv")
    cards: dict[str, dict] = {}
    ticks = _ticks(rows)
    totals = [sum(float(r["power_w"] or 0) for r in t) for t in ticks]
    hold_totals = [sum(float(r["power_w"] or 0) for r in t) for t in ticks if t and t[0]["phase"] == "hold"]
    for r in rows:
        if r["phase"] != "hold":
            continue
        c = cards.setdefault(r["uuid"], {"gpu": int(r["gpu"]), "temp": [], "fan": [], "power": [], "sm": [],
                                         "throttled": 0})
        c["temp"].append(float(r["temp_c"])); c["fan"].append(float(r["fan_pct"]))
        c["power"].append(float(r["power_w"])); c["sm"].append(float(r["sm_mhz"]))
        c["throttled"] += r["throttle"] not in ("0x0000000000000000", "")
    gpus = {}
    for uuid, c in cards.items():
        n = len(c["temp"]) or 1
        gpus[uuid] = {"gpu": c["gpu"], "samples": len(c["temp"]),
                      "temp_avg": round(sum(c["temp"]) / n, 1), "temp_max": max(c["temp"], default=0),
                      "fan_avg": round(sum(c["fan"]) / n, 1), "fan_max": max(c["fan"], default=0),
                      "power_avg": round(sum(c["power"]) / n, 1), "sm_avg": round(sum(c["sm"]) / n),
                      "throttled_pct": round(100 * c["throttled"] / n, 1)}
    summary = {"run": out.name, "gpus": gpus,
               "rig": {"peak_w": round(max(totals, default=0)),
                       "hold_avg_w": round(sum(hold_totals) / len(hold_totals)) if hold_totals else 0},
               **(extra or {})}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def print_compare(now: dict, before: dict) -> None:
    print(f"\ncompared with {before.get('run')} (cards matched by UUID; GPU index now / before):")
    print(f"  rig: peak {before['rig']['peak_w']} -> {now['rig']['peak_w']} W, "
          f"hold average {before['rig']['hold_avg_w']} -> {now['rig']['hold_avg_w']} W")
    for uuid, c in sorted(now["gpus"].items(), key=lambda kv: kv[1]["gpu"]):
        b = before["gpus"].get(uuid)
        if not b:
            print(f"  GPU{c['gpu']} {uuid[:12]}: new card, temp avg {c['temp_avg']} C, fan avg {c['fan_avg']}%")
            continue
        print(f"  GPU{c['gpu']}/{b['gpu']} {uuid[:12]}: temp avg {b['temp_avg']} -> {c['temp_avg']} C "
              f"(max {b['temp_max']} -> {c['temp_max']}), fan avg {b['fan_avg']} -> {c['fan_avg']}%, "
              f"power {b['power_avg']} -> {c['power_avg']} W, SM {b['sm_avg']} -> {c['sm_avg']} MHz")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--models", default=DEFAULT_MODELS, help="GPU=model,... (unnamed cards get a small model)")
    ap.add_argument("--uncap", action="store_true", help="factory power limits until the next boot")
    ap.add_argument("--spikes", action="store_true", help="reload each card under load after the hold")
    ap.add_argument("--ramp-s", type=int, default=60)
    ap.add_argument("--hold-s", type=int, default=600)
    ap.add_argument("--abort-gpu-c", type=float, default=88)
    ap.add_argument("--abort-cpu-c", type=float, default=95)
    ap.add_argument("--keep-loaded", action="store_true", help="leave the models loaded at the end")
    ap.add_argument("--hammer-after", type=int, help="keep this GPU at full load at the end (find it physically)")
    ap.add_argument("--compare", help="an earlier run's summary.json")
    ap.add_argument("--out", help="output folder (default ~/rig_stress/<time>)")
    ap.add_argument("--summarize", help="only (re)write DIR/summary.json from its stream.csv")
    a = ap.parse_args()
    if a.summarize:
        s = summarize(Path(a.summarize))
        print(json.dumps(s["rig"]))
        if a.compare:
            print_compare(s, json.loads(Path(a.compare).read_text()))
        return 0
    return Run(a).main()


if __name__ == "__main__":
    sys.exit(main())
