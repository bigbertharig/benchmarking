"""Show how the loaded model's chat template ends the prompt and what it generates first."""
import json, sys, urllib.request

def post(path, body):
    req = urllib.request.Request("http://127.0.0.1:11434" + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=180))

props = json.load(urllib.request.urlopen("http://127.0.0.1:11434/props", timeout=10))
tpl = props.get("chat_template", "")
i = tpl.find("add_generation_prompt")
print("template generation block:\n" + tpl[i:i + 500] + "\n")
samples = sys.argv[1]
r = json.loads(open(samples).readline())
msgs = [{"role": m["role"], "content": m["content"]}
        for m in json.loads(r["arguments"]["gen_args_0"]["arg_0"][0])]
for label, kw in (("default", {}), ("enable_thinking=false", {"chat_template_kwargs": {"enable_thinking": False}})):
    prompt = post("/apply-template", dict({"messages": msgs}, **kw))["prompt"]
    out = post("/completion", {"prompt": prompt, "n_predict": 30, "temperature": 0})
    print(f"== {label}: prompt tail {prompt[-60:]!r}\n   raw gen {out['content'][:120]!r}")
