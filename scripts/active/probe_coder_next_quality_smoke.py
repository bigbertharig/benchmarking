#!/usr/bin/env python3
import argparse, datetime as dt, json, pathlib, time, urllib.request
p=argparse.ArgumentParser()
p.add_argument("--port",type=int,required=True)
p.add_argument("--label",required=True)
p.add_argument("--output",type=pathlib.Path,required=True)
a=p.parse_args()
prompts=[
    "Write a Python function merge_sorted(a, b) that merges two already sorted integer lists. Return only code.",
    "Return a JSON object with exactly the keys alpha and beta, where alpha is 7 and beta is the string done. Return only JSON.",
    "What integer does this Python code print? x = 0; for i in range(1, 6): x += i * i; print(x). Give only the integer.",
]
rows=[]
for prompt in prompts:
    body=json.dumps({"messages":[{"role":"user","content":prompt}],
                     "temperature":0,"seed":42,"max_tokens":384,"stream":False}).encode()
    req=urllib.request.Request(f"http://127.0.0.1:{a.port}/v1/chat/completions",body,
                               {"Content-Type":"application/json"})
    t=time.monotonic()
    with urllib.request.urlopen(req,timeout=900) as resp: result=json.load(resp)
    c=result["choices"][0]
    rows.append({"prompt":prompt,"content":c["message"].get("content"),
                 "finish_reason":c.get("finish_reason"),"usage":result.get("usage"),
                 "wall_seconds":round(time.monotonic()-t,3)})
receipt={"schema":"coder-next-quality-smoke/1","label":a.label,
         "recorded_at":dt.datetime.now(dt.timezone.utc).isoformat(),"cases":rows}
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(receipt,indent=2)+"\n")
print(json.dumps({"output":str(a.output),"finish_reasons":[x["finish_reason"] for x in rows],
                  "answers":[x["content"][:150] if x["content"] else "" for x in rows]}))