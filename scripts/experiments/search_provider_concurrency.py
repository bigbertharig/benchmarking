#!/usr/bin/env python3
"""Bounded SearXNG concurrency probe using the existing frozen search questions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import time
from urllib.parse import urlparse

from search_provider_benchmark import QUERIES, percent, searxng_search

def probe(query, endpoint, limit):
    started = time.monotonic()
    try:
        items, issues, status = searxng_search(query['query'], limit, endpoint)
        error = None
    except Exception as exc:
        items, issues, status, error = [], [], None, type(exc).__name__
    urls = list(dict.fromkeys(x.get('url') for x in items if x.get('url')))
    rank = next((index + 1 for index, url in enumerate(urls)
                 if any((urlparse(url).hostname or '').lower() == domain or
                        (urlparse(url).hostname or '').lower().endswith('.' + domain)
                        for domain in query['domains'])), None)
    limited = status == 429 or any(any(term in note.lower() for term in
                 ('429', 'rate limit', 'too many', 'throttl')) for note in issues)
    return {'query_id': query['id'], 'latency_seconds': round(time.monotonic()-started, 3),
            'http_status': status, 'result_count': len(items), 'unique_url_count': len(urls),
            'official_domain_rank': rank, 'rate_limit_signal': limited,
            'degraded': bool(issues), 'unresponsive_engines': issues[:5], 'error': error}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--searxng-url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--workers', type=int, nargs='+', default=[1, 2, 4])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--gap-seconds', type=float, default=2.0)
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    if not args.workers or any(n < 1 or n > 8 for n in args.workers) or not 1 <= args.repeats <= 10:
        parser.error('workers must be 1..8 and repeats 1..10')
    batches = []
    stopped_after_rate_limit = False
    for workers in args.workers:
        for repeat in range(1, args.repeats + 1):
            if batches and args.gap_seconds:
                time.sleep(args.gap_seconds)
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                rows = list(pool.map(lambda query: probe(query, args.searxng_url, args.limit), QUERIES))
            wall = round(time.monotonic() - started, 3)
            batch = {'workers': workers, 'repeat': repeat, 'wall_seconds': wall,
                     'throughput_qps': round(len(rows)/wall, 3) if wall else None,
                     'rows': rows}
            batches.append(batch)
            print(json.dumps({'workers': workers, 'repeat': repeat, 'wall_seconds': wall,
                'successful': sum(r['result_count'] > 0 and not r['error'] for r in rows),
                'rate_limit_signals': sum(r['rate_limit_signal'] for r in rows),
                'degraded': sum(r['degraded'] for r in rows)}), flush=True)
            if all(r['rate_limit_signal'] and r['result_count'] == 0 for r in rows):
                stopped_after_rate_limit = True
                break
        if stopped_after_rate_limit:
            break
    summary = {}
    for workers in args.workers:
        selected = [batch for batch in batches if batch['workers'] == workers]
        if not selected:
            continue
        rows = [row for batch in selected for row in batch['rows']]
        latencies = [row['latency_seconds'] for row in rows if not row['error']]
        summary[str(workers)] = {'requests': len(rows),
            'nonempty': sum(row['result_count'] > 0 and not row['error'] for row in rows),
            'official_top_5': sum(row['official_domain_rank'] is not None and row['official_domain_rank'] <= 5 for row in rows),
            'rate_limit_signals': sum(row['rate_limit_signal'] for row in rows),
            'degraded': sum(row['degraded'] for row in rows),
            'median_unique_urls': statistics.median(row['unique_url_count'] for row in rows),
            'median_latency_seconds': percent(latencies, 0.5),
            'p95_latency_seconds': percent(latencies, 0.95),
            'median_batch_seconds': round(statistics.median(batch['wall_seconds'] for batch in selected), 3),
            'median_throughput_qps': round(statistics.median(batch['throughput_qps'] for batch in selected), 3)}
    receipt = {'backend': 'searxng', 'query_set': 'search_provider_benchmark.QUERIES',
               'repeats': args.repeats, 'gap_seconds': args.gap_seconds,
               'stopped_after_rate_limit': stopped_after_rate_limit,
               'summary_by_workers': summary, 'batches': batches}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + '\n')
    print('SUMMARY ' + json.dumps(summary), flush=True)
    raise SystemExit(0 if not stopped_after_rate_limit and all(
        value['nonempty'] == value['requests'] and value['rate_limit_signals'] == 0
        for value in summary.values()) else 1)

if __name__ == '__main__':
    main()
