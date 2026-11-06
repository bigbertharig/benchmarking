#!/usr/bin/env python3
"""Parse generated Nemotron code without executing it."""
import ast
import json
import pathlib

root = pathlib.Path("/media/bryan/shared/plans/shoulders/benchmarking/results/runtime_experiments/nemotron_expert_sweep_20261106")
results = {}
for label in ("standard6", "standard5", "expert5", "expert4", "expert4_repeat"):
    receipt = json.loads((root / f"{label}_practical.json").read_text())
    content = receipt["content"]
    code = content.split(chr(96) * 3 + "python\n", 1)[1].split("\n" + chr(96) * 3, 1)[0]
    try:
        tree = ast.parse(code)
        classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
        tests = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
        results[label] = {"syntax": "valid", "classes": classes, "test_functions": tests}
    except SyntaxError as exc:
        results[label] = {"syntax": "invalid", "error": str(exc)}
(root / "practical_syntax_validation.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results))
