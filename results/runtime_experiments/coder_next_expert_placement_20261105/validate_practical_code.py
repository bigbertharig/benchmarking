#!/usr/bin/env python3
import json
import pathlib
import subprocess
import sys
import tempfile

root = pathlib.Path("/media/bryan/shared/plans/shoulders/benchmarking/results/runtime_experiments/coder_next_expert_placement_20261105")
results = {}
for label in ("expert", "standard"):
    receipt = json.loads((root / f"practical_{label}_32k.json").read_text())
    content = receipt["content"]
    code = content.split("```python\n", 1)[1].split("\n```", 1)[0]
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "generated.py"
        path.write_text(code + "\n")
        run = subprocess.run([sys.executable, "-I", str(path)], capture_output=True, text=True, timeout=30)
        results[label] = {"exit_code": run.returncode, "stdout": run.stdout[-1500:], "stderr": run.stderr[-1500:]}
(root / "practical_code_validation.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps({label: {"exit_code": value["exit_code"], "stderr_tail": value["stderr"][-400:]} for label, value in results.items()}))