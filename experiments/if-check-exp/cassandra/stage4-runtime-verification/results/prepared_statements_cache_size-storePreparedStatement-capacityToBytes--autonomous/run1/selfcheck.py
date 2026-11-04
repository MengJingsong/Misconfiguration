#!/usr/bin/env python3
"""Independent recomputation of the cluster-tier figures of the prepared_statements_cache_size run from the raw files
(summary.txt, samples.csv, histo-excerpt.txt of each k<MiB>/). Exit 0 iff every load-bearing check holds."""
import re, os, sys, csv
base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cluster')
V = [1, 4, 16, 64]; D = {}
for v in V:
    t = open(f'{base}/k{v}/summary.txt').read()
    g = lambda p: re.search(p, t)
    fin = g(r'COUNTERS final count=(\d+) evicted=(\d+) memtable_heap=(\d+)')
    hist = {m.group(1): int(m.group(3)) for m in re.finditer(r'HISTO (\S+) live_bytes=(\d+) live_objects=\d+ prepared_instances=(\d+)', t)}
    live = {m.group(1): int(m.group(2)) for m in re.finditer(r'HISTO (\S+) live_bytes=(\d+)', t)}
    D[v] = dict(count=int(fin.group(1)), ev=int(fin.group(2)), mt=int(fin.group(3)), live=live, inst=hist,
                prepared=int(g(r'RESULT load offered=\d+ prepared=(\d+)').group(1)), rows=int(g(r'ROWS system.prepared_statements: (\d+)').group(1)),
                oversize=g(r'RESULT oversize .*? (rejected|accepted) (.*)'), samples=list(csv.DictReader(open(f'{base}/k{v}/samples.csv'))))
ok = True
def chk(name, cond, detail):
    global ok; ok &= bool(cond); print(('OK   ' if cond else 'FAIL ') + name + ' ' + detail)
for v in V:
    d = D[v]; cap = v << 20; w = cap / d['count']
    chk(f'k{v} count==rows', d['count'] == d['rows'], f"count={d['count']} rows={d['rows']} w={w:.1f}")
    chk(f'k{v} Prepared instances == count + 31', d['inst']['2-after-load'] == d['count'] + 31, f"instances={d['inst']['2-after-load']}")
    last10 = [int(s['count']) for s in d['samples']][-10:]
    chk(f'k{v} last 10 samples constant', len(last10) == 10 and max(last10) - min(last10) <= 0.01 * max(last10), f'{min(last10)}..{max(last10)}')
    chk(f'k{v} evicted >= 5x count', d['ev'] >= 5 * d['count'], f"evicted={d['ev']}")
    chk(f'k{v} count+evicted-prepared small', 0 <= d['count'] + d['ev'] - d['prepared'] <= 40, f"{d['count'] + d['ev'] - d['prepared']} (1 dup + 10 hot prepares = 11, plus driver re-prepares of evicted hot statements)")
c1 = D[1]['count']
for v in V[1:]:
    chk(f'count(k{v})/count(k1) == {v}', abs(D[v]['count'] / c1 - v) / v < 0.005, f"{D[v]['count'] / c1:.3f}")
print('oversize:', {v: (D[v]['oversize'].group(1), D[v]['oversize'].group(2)[60:150]) for v in V})
chk('oversize refused by the guard at 1 and 4 MiB', all('larger than allowed maximum' in D[v]['oversize'].group(2) for v in (1, 4)), '')
chk('oversize at 16 and 64 MiB refused by the transport, not the guard', all('exceeds allowed maximum of 16777216' in D[v]['oversize'].group(2) for v in (16, 64)), '')
dl = {v: D[v]['live']['2-after-load'] - D[v]['live']['1-after-plain'] for v in V}
plain = {v: D[v]['live']['1-after-plain'] - D[v]['live']['0-baseline'] for v in V}
print('live delta after load vs after-plain:', dl); print('plain-control growth:', plain)
for v in (4, 16):
    dcap = (v - 1) * (1 << 20) * 0.9998
    r = (dl[v] - dl[1]) / dcap
    chk(f'k{v}-k1 live delta / weight delta (same offered n)', 0.7 < r < 0.9, f'{r:.3f} (offered {D[v]["prepared"]} vs {D[1]["prepared"]})')
print('whole-JVM growth that does not depend on the knob (k1):', dl[1], 'B =', round(dl[1] / D[1]['prepared']), 'B per PREPARE;  plain control:', plain[1], 'B for 20,000 queries')
chk('plain control growth < 3 MB', all(p < 3e6 for p in plain.values()), str(plain))
chk('load growth at k1 > 60x the plain control growth', dl[1] > 60 * plain[1], f'{dl[1] / plain[1]:.0f}x')
print('RESULT', 'ALL HOLD' if ok else 'FAILURES'); sys.exit(0 if ok else 1)
