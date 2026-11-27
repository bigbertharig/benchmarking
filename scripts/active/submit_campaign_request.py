#!/usr/bin/env python3
"""Submit a simple benchmark request as one managed, resumable rig run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from build_campaign_request import ROOT, compile_request
from build_campaign_bundle import verify as verify_bundle
from export_model_library import build as build_export


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def submit(request_path: Path, *, pi_shared_root: Path, rig_shared_root: Path,
           rigctl: Path, run_id: str, rig_benchmarking_root: Path,
           dry_run: bool = False, max_active_models: int | None = None) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", run_id):
        raise ValueError("run_id must be 1-64 letters, digits, dots, underscores or dashes")
    if max_active_models is not None and max_active_models < 1:
        raise ValueError("max_active_models must be at least 1")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "model_registry.json").read_text(encoding="utf-8"))
    contracts = json.loads((ROOT / "docker" / "suite_contracts.json").read_text(encoding="utf-8"))
    source = json.loads((ROOT / "model_library_export.json").read_text(encoding="utf-8"))
    source_hash = source.get("source_sha256")
    if not source_hash:
        raise ValueError("Benchmarking model export has no source hash; regenerate it before submitting")
    if (ROOT / "campaign_bundle.json").exists():
        verify_bundle(ROOT)
        payload = {key: value for key, value in source.items() if key != "source_sha256"}
        canonical_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                                   ensure_ascii=True).encode("utf-8")).hexdigest()
        if canonical_hash != source_hash:
            raise ValueError("Benchmarking model export has an invalid source hash")
    elif build_export()["source_sha256"] != source_hash:
        raise ValueError("Benchmarking model export is stale; regenerate it before submitting")
    relative_dir = Path("logs/benchmarks/campaigns/requests")
    campaign = compile_request(request, registry, contracts)
    pi_campaign_dir = pi_shared_root / relative_dir
    rig_campaign_dir = rig_shared_root / relative_dir
    manifest_name = f"{run_id}.json"
    local_manifest = pi_campaign_dir / manifest_name
    rig_manifest = rig_campaign_dir / manifest_name
    status_relative = Path("logs/benchmarks/campaigns/history") / campaign["name"] / run_id / "status.json"
    rig_status = rig_shared_root / status_relative
    pi_status = pi_shared_root / status_relative
    base = {"schema": "benchmark-submission/1", "run_id": run_id, "campaign": campaign["name"],
            "model_library_sha256": source_hash,
            "blocks": len(campaign["blocks"]), "manifest": str(local_manifest),
            "rig_manifest": str(rig_manifest), "rig_status": str(rig_status),
            "pi_status": str(pi_status),
            "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **({"max_active_models": max_active_models} if max_active_models is not None else {})}
    if dry_run:
        return {**base, "state": "dry_run", "compiled_campaign": campaign}
    if local_manifest.exists():
        prior = json.loads(local_manifest.read_text(encoding="utf-8"))
        if prior != campaign:
            raise ValueError(f"run_id {run_id} already has a different manifest")
    else:
        _write_atomic(local_manifest, campaign)
    command = [sys.executable, str(rigctl), "run-start", "--run", run_id, "--auto-resume", "--",
               "python3", str(rig_benchmarking_root / "scripts" / "active" / "run_campaign.py"),
               str(rig_manifest), "--run-id", run_id]
    if max_active_models is not None:
        command += ["--max-active-models", str(max_active_models)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    try:
        manager = json.loads(result.stdout)
    except ValueError:
        manager = {"stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]}
    receipt = {**base, "state": "submitted" if result.returncode == 0 else "submission_failed",
               "manager_exit_code": result.returncode, "manager": manager}
    _write_atomic(pi_campaign_dir / f"{run_id}.submission.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--pi-shared-root", type=Path, required=True,
                        help="shared storage root as seen by the controller")
    parser.add_argument("--rig-shared-root", type=Path, required=True,
                        help="same shared storage root as seen by the rig")
    parser.add_argument("--rig-benchmarking-root", "--rig-campaign-package-root", type=Path, required=True,
                        help="Benchmarking campaign package or checkout path on the rig")
    parser.add_argument("--rigctl", type=Path, required=True, help="Gateway rigctl.py on this controller")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dry-run", action="store_true", help="compile and print; do not write or submit")
    parser.add_argument("--max-active-models", type=int, default=None, metavar="N",
                        help="Limit concurrently loaded models (use 1 for serial runtime measurements)")
    args = parser.parse_args()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("bench-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6]
    try:
        receipt = submit(args.request, pi_shared_root=args.pi_shared_root,
                         rig_shared_root=args.rig_shared_root, rigctl=args.rigctl,
                         run_id=run_id, rig_benchmarking_root=args.rig_benchmarking_root,
                         dry_run=args.dry_run, max_active_models=args.max_active_models)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["state"] != "submission_failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
