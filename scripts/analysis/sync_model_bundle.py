#!/usr/bin/env python3
"""Mirror a model's GGUFs and named runtime artifacts into the canonical archive.

The live hotset stays in place. Copy with rsync partials, verify SHA-256, then
publish a manifest only after every required file matches.
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-id", required=True)
    ap.add_argument("--gguf-source", type=pathlib.Path, required=True)
    ap.add_argument("--archive-root", type=pathlib.Path, required=True)
    ap.add_argument("--artifact", action="append", default=[], metavar="NAME=DIR")
    ap.add_argument("--receipt", type=pathlib.Path, required=True)
    ap.add_argument("--bwlimit", default="15M")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.model_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for c in a.model_id):
        ap.error("model-id must be a simple lower-case directory name")
    ggufs = sorted(p for p in a.gguf_source.glob("*.gguf") if p.is_file())
    if not ggufs:
        ap.error("no GGUF source files")
    files = [(p, a.archive_root / a.model_id / p.name, "gguf") for p in ggufs]
    for spec in a.artifact:
        if "=" not in spec: ap.error("artifact must be NAME=DIR")
        name, raw = spec.split("=", 1)
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for c in name):
            ap.error("invalid artifact name")
        source = pathlib.Path(raw)
        if not source.is_dir(): ap.error("missing artifact directory: " + raw)
        for p in sorted(source.rglob("*")):
            if p.is_file() and not p.is_symlink():
                files.append((p, a.archive_root / a.model_id / "runtime" / name / p.relative_to(source), name))
    if a.dry_run:
        print(json.dumps({"model_id": a.model_id, "file_count": len(files),
                          "bytes": sum(p.stat().st_size for p, _, _ in files),
                          "destinations": [str(d) for _, d, _ in files]}, indent=2))
        return 0
    receipt = {"schema": "model-bundle-sync/1", "model_id": a.model_id,
               "started_at": utc(), "status": "running", "files": []}
    a.receipt.parent.mkdir(parents=True, exist_ok=True)
    def save():
        a.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    save()
    try:
        for source, dest, role in files:
            dest.parent.mkdir(parents=True, exist_ok=True)
            row = {"source": str(source), "archive": str(dest), "role": role,
                   "size_bytes": source.stat().st_size, "status": "copying"}
            receipt["files"].append(row); save()
            subprocess.run(["rsync", "-a", "--partial", "--partial-dir=.rsync-partial",
                            "--bwlimit=" + a.bwlimit, str(source), str(dest)], check=True)
            if dest.stat().st_size != row["size_bytes"]:
                raise ValueError("size mismatch: " + str(dest))
            row["status"] = "verifying"; save()
            source_hash, dest_hash = sha256(source), sha256(dest)
            if source_hash != dest_hash:
                raise ValueError("hash mismatch: " + str(dest))
            row.update({"status": "verified", "sha256": source_hash}); save()
            print("verified", role, dest.name, row["size_bytes"], flush=True)
        manifest = {"schema": "model-bundle/1", "model_id": a.model_id,
                    "created_at": utc(), "archive_root": str(a.archive_root / a.model_id),
                    "files": [{"relative_path": str(pathlib.Path(r["archive"]).relative_to(a.archive_root / a.model_id)),
                               "role": r["role"], "bytes": r["size_bytes"], "sha256": r["sha256"]}
                              for r in receipt["files"]],
                    "total_archive_bytes": sum(r["size_bytes"] for r in receipt["files"])}
        target = a.archive_root / a.model_id / "bundle_manifest.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, indent=2) + "\n")
        tmp.replace(target)
        receipt["manifest"] = str(target)
        receipt["status"] = "complete"
    except Exception as exc:
        receipt["status"] = "failed"; receipt["error"] = repr(exc)
    finally:
        receipt["finished_at"] = utc(); save()
        print(json.dumps({"status": receipt["status"], "receipt": str(a.receipt),
                          "error": receipt.get("error")}), flush=True)
    return 0 if receipt["status"] == "complete" else 1

if __name__ == "__main__":
    sys.exit(main())
