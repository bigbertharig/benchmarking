#!/usr/bin/env python3
"""Map selected host GPU IDs to local CUDA ordinals by PCI bus, not list order."""
import argparse
import csv
import io
import json
import subprocess
from pathlib import Path

from hardware_inventory import scan_cards, require_ids, docker_devices

IMAGE="4bfa1cb0a955"
BINARY=Path("/data/bench-staging/cuda-link-probe")

def parse_ids(value):
    ids=[int(part) for part in value.split(",")]
    if not ids or len(ids)!=len(set(ids)): raise ValueError("GPU IDs must be distinct")
    return ids

def pci_suffix(value):
    if len(value)<7: raise ValueError(f"invalid PCI bus: {value}")
    return value[-7:].upper()

def map_host_to_cuda(hosts, host_bus, cuda_rows):
    by_bus={pci_suffix(row["pci_bus_id"]):int(row["cuda_id"]) for row in cuda_rows}
    mapping={host:by_bus[pci_suffix(host_bus[host])] for host in hosts}
    if len(set(mapping.values()))!=len(hosts): raise RuntimeError("ambiguous CUDA mapping")
    return mapping

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host-gpus",required=True)
    ap.add_argument("--chat-host-gpus",required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--binary",type=Path,default=BINARY)
    args=ap.parse_args()
    hosts=parse_ids(args.host_gpus)
    chats=parse_ids(args.chat_host_gpus)
    if not set(chats).issubset(hosts): ap.error("chat host GPUs must be selected")
    cards=scan_cards()
    require_ids(hosts,cards)
    rows=subprocess.run(["nvidia-smi","--query-gpu=index,pci.bus_id",
                         "--format=csv,noheader"],capture_output=True,text=True,
                        timeout=10,check=True).stdout.splitlines()
    host_bus={}
    for row in rows:
        fields=[x.strip() for x in row.split(",")]
        if len(fields)!=2 or not fields[0].isdigit(): raise RuntimeError(f"invalid PCI row: {row}")
        host_bus[int(fields[0])]=fields[1]
    require_ids(hosts,host_bus)
    command=["docker","run","--rm","--gpus",docker_devices(hosts,cards),
             "--network","none","-v",f"{args.binary.parent}:/probe:ro",
             "--entrypoint",f"/probe/{args.binary.name}",IMAGE,"--list"]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30,check=True)
    cuda_rows=list(csv.DictReader(io.StringIO(result.stdout)))
    mapping=map_host_to_cuda(hosts,host_bus,cuda_rows)
    record={"host_to_cuda":mapping,"host_pci_bus":{host:host_bus[host] for host in hosts},
            "cuda_devices":cuda_rows,"host_gpu_uuids":{host:cards[host]["uuid"] for host in hosts}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+"\n")
    print(",".join(str(mapping[host]) for host in chats))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
