#!/usr/bin/env python3
"""Summarize one decode-only Nsight SQLite capture by CUDA device."""
import argparse
import json
import re
import sqlite3
from pathlib import Path

def union_ms(intervals):
    spans=sorted((int(start),int(end)) for start,end in intervals if start is not None)
    if not spans: return 0.0
    merged=[]
    for start,end in spans:
        if merged and start<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(merged[-1][1],end))
        else:
            merged.append((start,end))
    return round(sum(end-start for start,end in merged)/1e6,3)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sqlite",type=Path,required=True)
    ap.add_argument("--log",type=Path,required=True)
    ap.add_argument("--worker-cuda",type=int,default=1)
    ap.add_argument("--model-cuda",type=int,default=0)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    log=a.log.read_text(errors="replace")
    m=re.search(r"GEN_METRIC phase=(\S+) name=(\w+) used=(\d+) tokens=(\d+) seconds=([\d.]+) tps=([\d.]+)",log)
    if not m: raise RuntimeError("generation metric absent")
    devices=dict((int(i),name.strip()) for i,name in re.findall(r"Device (\d+): ([^,]+)",log))
    conn=sqlite3.connect(a.sqlite)
    q=lambda sql,params=(): conn.execute(sql,params).fetchone()[0] or 0
    join="CUPTI_ACTIVITY_KIND_KERNEL k JOIN StringIds s ON k.demangledName=s.id"
    def ms(value): return round(value/1e6,3)
    def kernel_ms(device,pattern):
        return ms(q(f"SELECT SUM(k.end-k.start) FROM {join} WHERE k.deviceId=? AND s.value LIKE ?",(device,pattern)))
    worker=a.worker_cuda
    model=a.model_cuda
    copies={}
    for device in (model,worker):
        for kind,label in ((1,"h2d"),(2,"d2h"),(3,"d2d")):
            row=conn.execute("SELECT COUNT(*),SUM(bytes),SUM(end-start) FROM CUPTI_ACTIVITY_KIND_MEMCPY WHERE deviceId=? AND copyKind=?",(device,kind)).fetchone()
            copies[f"cuda{device}_{label}"]={"count":row[0],"MB":round((row[1] or 0)/1e6,3),"duration_ms":ms(row[2] or 0)}
    busy={}
    for device in (model,worker):
        intervals=[]
        for table in ("CUPTI_ACTIVITY_KIND_KERNEL","CUPTI_ACTIVITY_KIND_MEMCPY","CUPTI_ACTIVITY_KIND_GRAPH_TRACE"):
            intervals+=conn.execute(f"SELECT start,end FROM {table} WHERE deviceId=?",(device,)).fetchall()
        busy[f"cuda{device}"]=union_ms(intervals)
    result={
      "phase":m.group(1),"chat":m.group(2),"occupied":int(m.group(3)),
      "tokens":int(m.group(4)),"wall_seconds":float(m.group(5)),"tok_s":float(m.group(6)),
      "devices":devices,"worker_cuda":worker,"model_cuda":model,
      "worker_kernels_ms":{
        "all":ms(q("SELECT SUM(end-start) FROM CUPTI_ACTIVITY_KIND_KERNEL WHERE deviceId=?",(worker,))),
        "attention_tile":kernel_ms(worker,"%flash_attn_tile%"),
        "attention_vector":kernel_ms(worker,"%flash_attn_ext_vec%"),
        "q41_dequant":kernel_ms(worker,"%dequantize_block_q4_1%")},
      "model_graph_ms":ms(q("SELECT SUM(end-start) FROM CUPTI_ACTIVITY_KIND_GRAPH_TRACE WHERE deviceId=?",(model,))),
      "copies":copies,"device_activity_union_ms":busy,
      "note":"Kernel, graph, and copy duration sums can overlap; activity union is per device, not a wall-time decomposition."}
    conn.close()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"phase":result["phase"],"tok_s":result["tok_s"],"worker":devices.get(worker)}))
if __name__=="__main__":
    main()
