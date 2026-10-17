import json,sys,glob,re
for run in sys.argv[1:]:
    files=glob.glob(f"/mnt/shared/logs/benchmarks/bench-reasoning/history/*{run}/bbh/*/samples_*.jsonl")
    n=right=nophrase=wrong=trunc=0
    for f in files:
        for l in open(f):
            r=json.loads(l); n+=1
            resp=str(r["resps"][0][0]); em=r.get("exact_match",0)
            if em: right+=1
            elif not re.search(r"(?i)the answer is", resp): nophrase+=1; trunc+= len(resp)>1500
            else: wrong+=1
    print(f"{run}: n={n} right={right} wrong_answer={wrong} no_answer_phrase={nophrase} (long/likely cut={trunc})")
