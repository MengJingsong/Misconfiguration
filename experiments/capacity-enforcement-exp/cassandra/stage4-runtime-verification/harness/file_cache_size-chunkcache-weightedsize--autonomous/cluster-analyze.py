#!/usr/bin/env python3
"""Cluster-tier analyzer of file_cache_size-chunkcache-weightedsize--autonomous (B3f, B3g; terms of AM2 and AM8).
usage: cluster-analyze.py <samples.jsonl>
Steady = read-phase samples from 180 s after the first read sample to the end of the read phase (AM8)."""
import json, statistics, sys

MiB = 1 << 20
SLACK = 32 * 16 * 1024          # 32 threads x 16 KiB chunk (B3f)
recs = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
settings = []
for r in recs:
    if r['setting'] not in settings:
        settings.append(r['setting'])
BANDS = {64: (29 * MiB, 32 * MiB), 256: (200 * MiB, 224 * MiB), 512: (430 * MiB, 480 * MiB)}
checks = []


def check(label, cond, detail):
    checks.append(cond)
    print(f'EXPECTED {"PASS" if cond else "FAIL"}: {label} -- {detail}')


def m(x):
    return 'NA' if x is None else f'{x / MiB:.2f} MiB'


summ = {}
for s in settings:
    rs = [r for r in recs if r['setting'] == s]
    idle = [r for r in rs if r['stage'] == 'idle']
    read = [r for r in rs if r['stage'] == 'read']
    post = [r for r in rs if r['stage'] == 'post']
    t0 = read[0]['t_ms']
    steady = [r for r in read if r['t_ms'] - t0 >= 180000]
    if not steady:
        steady = read[len(read) // 2:]
    print(f'\n=== setting {s}: idle {len(idle)}, read {len(read)} (steady {len(steady)}), post {len(post)} samples')
    print('  stage  +s   cc_size      entries  pool_size   overflow   net_size   direct_used  nmt_other  rss_anon   requests  misses')
    for r in rs:
        print(f"  {r['stage']:5s} {(r['t_ms'] - t0) / 1000:6.0f} {str(r.get('cc_size')):>12s} {str(r.get('cc_entries')):>7s} "
              f"{str(r.get('pool_size')):>10s} {str(r.get('pool_overflow')):>9s} {str(r.get('net_size')):>9s} {str(r.get('direct_used')):>11s} "
              f"{str(r.get('nmt_other_committed_kb')):>9s}K {str(r.get('rss_anon_kb')):>8s}K {str(r.get('cc_requests')):>9s} {str(r.get('cc_misses')):>8s}")
    d = {
        'direct_steady_median': statistics.median(r['direct_used'] for r in steady),
        'direct_idle_median': statistics.median(r['direct_used'] for r in idle),
        'pool_max_read': max(r['pool_size'] for r in read),
        'pool_steady_median': statistics.median(r['pool_size'] for r in steady),
        'ovf_max_read': max(r['pool_overflow'] for r in read),
        'ovf_steady_first': steady[0]['pool_overflow'], 'ovf_steady_last': steady[-1]['pool_overflow'],
        'nmt_steady_median': statistics.median(r['nmt_other_committed_kb'] for r in steady) * 1024,
        'rss_steady_median': statistics.median(r['rss_anon_kb'] for r in steady) * 1024,
        'net_max_read': max(r['net_size'] for r in read),
    }
    if s != 'disabled':
        cap = read[0]['cc_capacity']
        d.update({
            'capacity': cap,
            'cc_max_read': max(r['cc_size'] for r in read),
            'cc_min_steady': min(r['cc_size'] for r in steady),
            'cc_max_steady': max(r['cc_size'] for r in steady),
            'cc_idle_max': max(r['cc_size'] for r in idle),
            'cc_first_read': read[0]['cc_size'],
            'req_delta': read[-1]['cc_requests'] - read[0]['cc_requests'],
            'miss_delta': read[-1]['cc_misses'] - read[0]['cc_misses'],
            'entries_steady_max': max(r['cc_entries'] for r in steady),
        })
    summ[s] = d
    print('  summary: ' + ', '.join(f'{k}={v if isinstance(v, (int, float)) and k.endswith(("delta", "entries_steady_max")) else m(v)}' for k, v in d.items()))

print('\n=== checks (B3f, B3g, AM2, AM8)')
base = summ.get('disabled')
if base:
    p = base['pool_max_read']
    check('disabled: pool Size small, multiple of 8 MiB, <= 32 MiB (B3f as amended by AM2)', p % (8 * MiB) == 0 and p <= 32 * MiB, f'pool max during read {m(p)} (overflow max {m(base["ovf_max_read"])})')
deltas = {}
for s in [x for x in settings if x != 'disabled']:
    d = summ[s]
    n = int(s)
    cs = (n - 32) * MiB
    lo, hi = BANDS.get(n, (0.9 * cs, cs))
    check(f'{n}: capacity == (N-32) MiB', d['capacity'] == cs, f"capacity {m(d['capacity'])}")
    check(f'{n}: plateau -- every steady read sample in [{m(lo)}, {m(hi + SLACK)}] (AM8)', lo <= d['cc_min_steady'] and d['cc_max_steady'] <= hi + SLACK,
          f"steady cc_size {m(d['cc_min_steady'])} .. {m(d['cc_max_steady'])}")
    check(f'{n}: no read sample above capacity + 512 KiB (not "exceeds persistently")', d['cc_max_read'] <= d['capacity'] + SLACK, f"max read cc_size {m(d['cc_max_read'])}")
    check(f'{n}: pool Size <= N MiB + OverflowSize (B3f)', d['pool_max_read'] <= n * MiB + d['ovf_max_read'], f"pool max {m(d['pool_max_read'])}, overflow max {m(d['ovf_max_read'])}")
    check(f'{n}: overflow not climbing (<= 16 MiB, steady rise <= 16 MiB; AM8)', d['ovf_max_read'] <= 16 * MiB and d['ovf_steady_last'] - d['ovf_steady_first'] <= 16 * MiB,
          f"overflow max {m(d['ovf_max_read'])}, steady {m(d['ovf_steady_first'])} -> {m(d['ovf_steady_last'])}")
    print(f"INFO {n}: overflow ~0 (<= 1 MiB)? {d['ovf_max_read'] <= MiB}")
    check(f'{n}: idle samples show ~no cache memory before reads; size rises under reads (positive control)', d['cc_idle_max'] <= 16 * MiB and d['cc_max_read'] >= 0.9 * cs,
          f"idle max {m(d['cc_idle_max'])}, first read sample {m(d['cc_first_read'])}, read max {m(d['cc_max_read'])}")
    check(f'{n}: Requests grow during reads; misses far above entries (cache on the read path; disallow evidence)', d['req_delta'] > 0 and d['miss_delta'] > 2 * d['entries_steady_max'],
          f"requests +{d['req_delta']}, misses +{d['miss_delta']}, entries <= {d['entries_steady_max']}")
    if base:
        delta = d['direct_steady_median'] - base['direct_steady_median']
        deltas[n] = delta
        check(f'{n}: direct delta about N: in [cacheSize - 16 MiB, N + 16 MiB] (AM8)', cs - 16 * MiB <= delta <= (n + 16) * MiB,
              f"direct steady median {m(d['direct_steady_median'])} - baseline {m(base['direct_steady_median'])} = {m(delta)}")
        print(f"INFO {n}: NMT Other delta {m(d['nmt_steady_median'] - base['nmt_steady_median'])}, RssAnon delta {m(d['rss_steady_median'] - base['rss_steady_median'])}, pool steady median {m(d['pool_steady_median'])}")
if len(deltas) >= 2:
    ks = sorted(deltas)
    check('direct deltas rise with N (monotone)', all(deltas[a] < deltas[b] for a, b in zip(ks, ks[1:])), ', '.join(f'{k}: {m(deltas[k])}' for k in ks))
    if 64 in deltas and 512 in deltas:
        check('delta(512) - delta(64) >= 64 MiB (not "512 ~ 64")', deltas[512] - deltas[64] >= 64 * MiB, m(deltas[512] - deltas[64]))
print(f'\nSUMMARY {sum(checks)} PASS, {len(checks) - sum(checks)} FAIL')
