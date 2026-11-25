#!/usr/bin/env python3
"""Small, repeatable direct search baseline for future harness search trials."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError


QUERIES = [
    {'id': 'python_taskgroup', 'query': 'Python asyncio TaskGroup official documentation', 'domains': ['docs.python.org']},
    {'id': 'mdn_urlsearchparams', 'query': 'MDN URLSearchParams reference', 'domains': ['developer.mozilla.org']},
    {'id': 'sqlite_wal', 'query': 'SQLite write ahead logging official documentation', 'domains': ['sqlite.org']},
    {'id': 'numpy_broadcasting', 'query': 'NumPy broadcasting official documentation', 'domains': ['numpy.org']},
]


def ddg_search(query, limit):
    from rig_search.duckduckgo import search
    result = search(query, limit)
    return result['results'], [result['error']] if result.get('error') else [], 429 if result.get('rate_limit_signal') else None


def searxng_search(query, limit, endpoint):
    url = endpoint.rstrip('/') + '/search?' + urlencode({'q': query, 'format': 'json', 'pageno': 1})
    req = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'harness-search-benchmark/1'})
    try:
        with urlopen(req, timeout=20) as response:
            packet = json.load(response)
            status = response.status
    except HTTPError as exc:
        return [], [f'HTTP {exc.code}'], exc.code
    items = packet.get('results', [])[:limit]
    failures = []
    for issue in packet.get('unresponsive_engines', []):
        if isinstance(issue, (list, tuple)) and len(issue) >= 2:
            failures.append(f'{issue[0]}: {issue[1]}')
        elif isinstance(issue, dict):
            failures.append(f"{issue.get('engine', '?')}: {issue.get('reason', issue.get('error', '?'))}")
    return [{'url': x.get('url'), 'title': x.get('title', ''),
             'snippet': x.get('content', '')} for x in items], failures, status


def percent(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered)-1, max(0, int((len(ordered)-1)*pct)))], 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', choices=['ddg', 'searxng'], required=True)
    parser.add_argument('--searxng-url', default=os.environ.get('SEARXNG_URL'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--rounds', choices=['paced', 'burst', 'both'], default='both')
    parser.add_argument('--pace-seconds', type=float, default=1.0,
                        help='Delay between paced requests; use a few minutes for recovery checks')
    parser.add_argument('--query-prefix', default='',
                        help='Optional SearXNG engine bang, such as !bi, for fallback diagnostics')
    parser.add_argument('--query-id', choices=[q['id'] for q in QUERIES])
    args = parser.parse_args()
    if args.backend == 'searxng' and not args.searxng_url:
        parser.error('SearXNG requires --searxng-url or SEARXNG_URL')
    if not 0 <= args.pace_seconds <= 3600:
        parser.error('--pace-seconds must be between 0 and 3600')
    if args.query_prefix and (args.backend != 'searxng' or not args.query_prefix.startswith('!') or
                              any(char.isspace() for char in args.query_prefix)):
        parser.error('--query-prefix must be a SearXNG engine bang without spaces')
    rows = []
    started_utc = datetime.now(timezone.utc).isoformat()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rounds = [('paced', args.pace_seconds), ('burst', 0.0)]
    for round_name, pause in rounds:
        if args.rounds not in ('both', round_name):
            continue
        for query in (q for q in QUERIES if args.query_id in (None, q['id'])):
            search_query = (args.query_prefix + ' ' + query['query']).strip()
            if pause and rows:
                time.sleep(pause)
            started = time.monotonic()
            try:
                if args.backend == 'ddg':
                    items, logs, status = ddg_search(search_query, args.limit)
                else:
                    items, logs, status = searxng_search(search_query, args.limit, args.searxng_url)
                error = None
            except Exception as exc:
                items, logs, status, error = [], [], None, type(exc).__name__ + ': ' + str(exc)
            elapsed = round(time.monotonic() - started, 3)
            urls = [x['url'] for x in items if x.get('url')]
            unique = list(dict.fromkeys(urls))
            expected_rank = next((i + 1 for i, link in enumerate(unique)
                                  if any(urlparse(link).hostname == domain or
                                         (urlparse(link).hostname or '').endswith('.' + domain)
                                         for domain in query['domains'])), None)
            signal = status == 429 or any('429' in line or 'rate limit' in line.lower() or 'too many' in line.lower() or 'thrott' in line.lower()
                                           for line in logs)
            rows.append({'round': round_name, 'query_id': query['id'], 'query': search_query,
                         'latency_seconds': elapsed, 'result_count': len(items), 'unique_url_count': len(unique),
                         'expected_domain_rank': expected_rank, 'expected_domain_top_5': expected_rank is not None and expected_rank <= 5,
                         'http_status': status, 'rate_limit_signal': signal, 'empty_result': not items,
                         'degraded': args.backend == 'searxng' and bool(logs),
                         'error': error, 'urls': unique, 'logs': logs[-5:]})
            args.out.write_text(json.dumps({'state': 'running', 'backend': args.backend,
                'started_utc': started_utc,
                'last_progress_utc': datetime.now(timezone.utc).isoformat(),
                'pace_seconds': args.pace_seconds, 'query_prefix': args.query_prefix,
                'rows': rows}, indent=2) + '\n')
            print(json.dumps({k: rows[-1][k] for k in ('round', 'query_id', 'latency_seconds', 'unique_url_count',
                                                       'expected_domain_rank', 'rate_limit_signal', 'error')}), flush=True)
    latency = [x['latency_seconds'] for x in rows if not x['error']]
    summary = {'backend': args.backend, 'queries': len({x['query_id'] for x in rows}), 'requests': len(rows),
               'state': 'complete', 'started_utc': started_utc,
               'finished_utc': datetime.now(timezone.utc).isoformat(),
               'pace_seconds': args.pace_seconds,
               'query_prefix': args.query_prefix,
               'successful_nonempty': sum(not x['empty_result'] and not x['error'] for x in rows),
               'expected_domain_top_5': sum(x['expected_domain_top_5'] for x in rows),
               'rate_limit_signals': sum(x['rate_limit_signal'] for x in rows),
               'degraded_responses': sum(x['degraded'] for x in rows),
               'empty_results': sum(x['empty_result'] for x in rows),
               'median_latency_seconds': percent(latency, 0.5), 'p95_latency_seconds': percent(latency, 0.95),
               'median_unique_urls': statistics.median([x['unique_url_count'] for x in rows]),
               'rows': rows}
    args.out.write_text(json.dumps(summary, indent=2) + '\n')
    print('SUMMARY ' + json.dumps({k: v for k, v in summary.items() if k != 'rows'}), flush=True)
    raise SystemExit(0 if summary['successful_nonempty'] == len(rows) else 1)


if __name__ == '__main__':
    main()
