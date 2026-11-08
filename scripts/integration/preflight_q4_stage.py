#!/usr/bin/env python3
"""Check staged Q4 shards and space; reuse prior hashes for unchanged files."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

MODEL = Path('/data/model-hotset/qwen3.8-flash-next-ud-q4_k_xl')
MANIFEST = MODEL / 'bundle_manifest.json'
MIN_FREE = 3 * 1024**3


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--quick', action='store_true',
                    help='reuse a passed full-hash receipt if size and file timestamps are unchanged')
    args = ap.parse_args()
    spec = json.loads(MANIFEST.read_text())
    if spec.get('schema') != 'model-bundle/1' or len(spec.get('files', [])) != 4:
        raise RuntimeError('unexpected Q4 bundle manifest')
    full_receipt = MODEL / 'runtime' / 'q4_stage_preflight.json'
    previous = None
    previous_by_path = {}
    if args.quick:
        previous = json.loads(full_receipt.read_text())
        if previous.get('status') != 'passed' or len(previous.get('files', [])) != 4:
            raise RuntimeError('no passed full-hash receipt; rerun without --quick')
        previous_by_path = {row['path']: row for row in previous['files']}
        checked_epoch = datetime.fromisoformat(previous['checked_at']).timestamp()
    checked = []
    for entry in spec['files']:
        path = MODEL / entry['relative_path']
        if not path.is_file() or path.stat().st_size != entry['bytes']:
            raise RuntimeError(f'missing or wrong-size shard: {path}')
        if args.quick:
            prior = previous_by_path.get(str(path))
            if (not prior or prior.get('bytes') != entry['bytes']
                    or prior.get('sha256') != entry['sha256']):
                raise RuntimeError(f'full-hash receipt does not match manifest: {path}')
            stat = path.stat()
            if max(stat.st_mtime, stat.st_ctime) > checked_epoch:
                raise RuntimeError(f'shard changed since full hash; rerun without --quick: {path}')
            checked.append(prior)
            print(f'reused verified hash for {path.name}', flush=True)
        else:
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != entry['sha256']:
                raise RuntimeError(f'hash mismatch: {path}')
            checked.append({'path': str(path), 'bytes': entry['bytes'], 'sha256': digest.hexdigest()})
            print(f'verified {path.name}', flush=True)
    stats = os.statvfs(MODEL)
    free = stats.f_bavail * stats.f_frsize
    if free < MIN_FREE:
        raise RuntimeError(f'NVMe free space {free} below {MIN_FREE}')
    receipt = {'status': 'passed', 'checked_at': datetime.now(timezone.utc).isoformat(),
               'mode': 'receipt_reuse' if args.quick else 'full_sha256',
               'full_hash_checked_at': previous['checked_at'] if previous else None,
               'files': checked, 'nvme_free_bytes': free, 'required_free_bytes': MIN_FREE}
    out = MODEL / 'runtime' / ('q4_quick_preflight.json' if args.quick else 'q4_stage_preflight.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix('.tmp')
    temp.write_text(json.dumps(receipt, indent=2) + '\n')
    os.replace(temp, out)
    print(out, flush=True)


if __name__ == '__main__':
    main()
