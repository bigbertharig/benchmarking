#!/usr/bin/env python3
"""Run the CUDA copy-path probe with live GPU inventory and durable receipts."""
import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from hardware_inventory import scan_cards, require_ids, check_planned_power

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--gpus",required=True,help="comma-separated host GPU IDs")
    ap.add_argument("--binary",type=Path,default=Path("/data/bench-staging/cuda-link-probe"))
    args=ap.parse_args()
    ids=[int(x) for x in args.gpus.split(",")]
    if not ids or len(ids)!=len(set(ids)): ap.error("GPU IDs must be unique")
    cards=scan_cards()
    require_ids(ids,cards)
    check_planned_power(ids)
    busy=[i for i in ids if cards[i]["used_mib"]>1024]
    if busy: raise RuntimeError(f"selected GPUs busy: {busy}")
    if not args.binary.is_file(): raise FileNotFoundError(args.binary)
    bus_output=subprocess.run(["nvidia-smi","--query-gpu=index,pci.bus_id","--format=csv,noheader"],
                              capture_output=True,text=True,check=True,timeout=10).stdout
    buses={}
    for line in bus_output.splitlines():
        parts=[x.strip() for x in line.split(",")]
        if len(parts)!=2 or not parts[0].isdigit(): raise RuntimeError(f"invalid PCI inventory: {line}")
        buses[int(parts[0])]=parts[1]
    require_ids(ids,buses)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/"inventory.json").write_text(json.dumps({i:{**cards[i],"pci_bus_id":buses[i]} for i in ids},indent=2)+"\n")
    command=["docker","run","--rm","--gpus","all","--network","none",
             "-v",f"{args.binary.parent}:/probe:ro",
             "--entrypoint",f"/probe/{args.binary.name}","4bfa1cb0a955",*(buses[i] for i in ids)]
    start=stamp()
    t0=time.monotonic()
    result=subprocess.run(command,capture_output=True,text=True,timeout=300)
    (args.output/"copies.csv").write_text(result.stdout)
    (args.output/"diagnostics.log").write_text(result.stderr)
    terminal={"started_at":start,"finished_at":stamp(),"duration_s":round(time.monotonic()-t0,3),
              "gpus":ids,"binary":str(args.binary),"exit_code":result.returncode,
              "status":"passed" if result.returncode==0 else "failed",
              "measurement":"CPU wall median, pinned host, isolated idle GPUs"}
    (args.output/"terminal.json").write_text(json.dumps(terminal,indent=2)+"\n")
    print(json.dumps(terminal))
    return result.returncode

if __name__=="__main__":
    raise SystemExit(main())
