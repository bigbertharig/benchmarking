#!/usr/bin/env python3
"""Read-only Linux hardware snapshot for expert placement research."""
import argparse
import csv
import datetime as dt
import json
import pathlib
import subprocess

def run(args):
    p = subprocess.run(args, capture_output=True, text=True, check=True)
    return p.stdout

def memory():
    rows = {}
    for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
            rows[key + "_bytes"] = int(value.strip().split()[0]) * 1024
    return rows

def gpus():
    fields = ["index", "uuid", "name", "memory.total", "memory.free",
              "pcie.link.gen.current", "pcie.link.width.current",
              "pcie.link.gen.max", "pcie.link.width.max"]
    raw = run(["nvidia-smi", "--query-gpu=" + ",".join(fields),
               "--format=csv,noheader,nounits"])
    result = []
    for row in csv.reader(raw.splitlines(), skipinitialspace=True):
        if len(row) != len(fields):
            raise ValueError(f"nvidia-smi returned {len(row)} fields: {row}")
        g = dict(zip(fields, (x.strip() for x in row)))
        for key in ("index", "memory.total", "memory.free",
                    "pcie.link.gen.current", "pcie.link.width.current",
                    "pcie.link.gen.max", "pcie.link.width.max"):
            g[key] = int(g[key])
        g["memory.total_bytes"] = g.pop("memory.total") * 1024 * 1024
        g["memory.free_bytes"] = g.pop("memory.free") * 1024 * 1024
        result.append(g)
    return result

def disks():
    data = json.loads(run(["lsblk", "-b", "-J", "-o",
                            "NAME,SIZE,ROTA,TYPE,MOUNTPOINT,TRAN"]))
    return data["blockdevices"]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=pathlib.Path, required=True)
    a = p.parse_args()
    result = {"schema": "expert-hardware-snapshot/1",
              "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "memory": memory(), "gpus": gpus(), "block_devices": disks(),
              "topology_text": run(["nvidia-smi", "topo", "-m"]),
              "pcie_note": "Current generation may downshift while idle; max is the reported link ceiling."}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(a.output), "gpus": len(result["gpus"]),
                      "mem_total_bytes": result["memory"]["MemTotal_bytes"]}))

if __name__ == "__main__":
    main()
