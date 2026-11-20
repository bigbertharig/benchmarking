#!/usr/bin/env python3
"""Verify local safetensors against the downloaded archive's SHA-256 ETags."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--min-files', type=int, default=1)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('verification receipt must be new')
    root = args.model_dir.resolve()
    files = sorted(path for path in root.rglob('*.safetensors') if '.cache' not in path.parts)
    if len(files) < args.min_files:
        parser.error(f'found only {len(files)} weight files')
    verified = []
    for path in files:
        relative = path.relative_to(root)
        metadata = root / '.cache' / 'huggingface' / 'download' / f'{relative}.metadata'
        expected = metadata.read_text(encoding='utf-8').splitlines()[1]
        if len(expected) != 64:
            raise ValueError(f'missing SHA-256 ETag for {relative}')
        with path.open('rb') as file:
            actual = hashlib.file_digest(file, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError(f'weight hash mismatch for {relative}: {actual} != {expected}')
        verified.append({'file': str(relative), 'bytes': path.stat().st_size,
                         'sha256': actual})
        print(f'{relative}: verified', flush=True)
    receipt = {'model_dir': str(root), 'verified_at': datetime.now(timezone.utc).isoformat(),
               'status': 'complete', 'verified_files': verified,
               'total_bytes': sum(item['bytes'] for item in verified)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(f'HOTSET_VERIFIED={len(verified)}/{len(files)} {args.output}', flush=True)


if __name__ == '__main__':
    main()
