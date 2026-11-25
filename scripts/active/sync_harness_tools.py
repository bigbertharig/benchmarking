#!/usr/bin/env python3
"""Import the harness-owned dashboard MCP catalog for model/tool tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


DESTINATION = Path(__file__).resolve().parents[2] / "tool_catalog.json"
VALID_APPROVALS = {"automatic", "disabled"}


def load_source(path: Path) -> dict:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("servers"), dict):
        raise ValueError("unsupported harness tool catalog schema")
    if not catalog["servers"] or any(not isinstance(name, str) or not name.isidentifier()
                                      for name in catalog["servers"]):
        raise ValueError("invalid dashboard MCP server")
    all_names = set()
    for server, entry in catalog["servers"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("tools"), list):
            raise ValueError(f"invalid tools for {server}")
        names = []
        for tool in entry["tools"]:
            if not isinstance(tool, dict) or set(tool) not in ({"name", "approval"}, {"name", "approval", "input_schema", "input_schema_sha256"}):
                raise ValueError(f"invalid tool entry for {server}")
            if 'input_schema' in tool:
                digest = hashlib.sha256(json.dumps(tool['input_schema'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
                if not isinstance(tool['input_schema'],dict) or tool.get('input_schema_sha256') != digest:
                    raise ValueError(f'invalid schema digest for {server}')
            name = tool["name"]
            if not isinstance(name, str) or not name.isidentifier() or tool["approval"] not in VALID_APPROVALS:
                raise ValueError(f"invalid tool name or approval for {server}")
            names.append(name)
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate tool for {server}")
        if all_names.intersection(names):
            raise ValueError(f"dashboard tool name collision in {server}")
        all_names.update(names)
    return catalog


def projection(source: Path) -> dict:
    catalog = load_source(source)
    return {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "servers": catalog["servers"],
    }


def changed(before: dict, after: dict) -> dict:
    old = {f"{server}.{tool['name']}": tool for server, entry in before.get("servers", {}).items()
           for tool in entry.get("tools", [])}
    new = {f"{server}.{tool['name']}": tool for server, entry in after["servers"].items()
           for tool in entry["tools"]}
    return {"added": sorted(new.keys() - old.keys()),
            "removed": sorted(old.keys() - new.keys()),
            "changed": sorted(key for key in old.keys() & new.keys() if old[key] != new[key])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="harness dashboard_tool_catalog.json")
    parser.add_argument("mode", choices=("what-new", "sync", "check"))
    args = parser.parse_args()
    try:
        after = projection(args.source)
        before = json.loads(DESTINATION.read_text(encoding="utf-8")) if DESTINATION.exists() else {}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    stale = any(before.get(key) != after[key] for key in after)
    print(json.dumps({"stale": stale, "source_sha256": after["source_sha256"],
                      "tools": changed(before, after)}, sort_keys=True))
    if args.mode == "check":
        return 1 if stale else 0
    if args.mode == "sync" and stale:
        after["imported_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=DESTINATION.parent,
                                             prefix=".tool_catalog.", suffix=".tmp", delete=False) as tmp:
                json.dump(after, tmp, indent=2, sort_keys=True)
                tmp.write("\n")
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_name = tmp.name
            os.replace(temp_name, DESTINATION)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
