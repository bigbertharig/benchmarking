"""Gateway tool import stays local and detects harness changes."""

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/active/sync_harness_tools.py"
spec = importlib.util.spec_from_file_location("sync_harness_tools", SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def test_tool_catalog_validates_and_reports_changes(tmp_path):
    source = tmp_path / "tools.json"
    source.write_text(json.dumps({"schema_version": 1, "servers": {
        "local_agents": {"purpose": "agents", "tools": [
            {"name": "list_local_agents", "approval": "automatic"}]},
        "rig_search": {"purpose": "search", "tools": [
            {"name": "search_web", "approval": "disabled"}]},
    }}))
    imported = sync.projection(source)
    assert sync.changed({}, imported)["added"] == ["local_agents.list_local_agents", "rig_search.search_web"]
    assert imported["source_sha256"]
    imported["servers"]["rig_search"]["tools"][0]["approval"] = "automatic"
    assert sync.changed(sync.projection(source), imported)["changed"] == ["rig_search.search_web"]


def test_invalid_schema_digest_preserves_last_valid_snapshot(tmp_path, monkeypatch):
    import pytest
    destination = tmp_path / 'current.json'
    destination.write_text('{"last_valid":true}')
    source = tmp_path / 'invalid.json'
    source.write_text(json.dumps({'schema_version':1,'servers':{'fixture':{'tools':[
        {'name':'read','approval':'automatic','input_schema':{'type':'object'},'input_schema_sha256':'wrong'}]}}}))
    monkeypatch.setattr(sync, 'DESTINATION', destination)
    monkeypatch.setattr('sys.argv', ['sync', '--source', str(source), 'sync'])
    with pytest.raises(SystemExit): sync.main()
    assert destination.read_text() == '{"last_valid":true}'
