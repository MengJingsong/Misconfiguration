#!/usr/bin/env python3
"""Cluster tier: compare the phase outputs with the frozen predictions (case file B3f as made numeric in B3i.4).
Usage: analyze_cluster.py <outdir>   Recomputes everything from samples-*.csv / info-*.csv / phase-*.json."""
import sys, os, json, csv
out = sys.argv[1]; MiB = 1 << 20
R = []
def chk(n, ok, d): R.append(('PASS' if ok else 'FAIL', n, d))
def samples(l): return [(int(r['epoch_ms']), int(r['rss_anon_kb'])) for r in csv.DictReader(open(os.path.join(out, 'samples-%s.csv' % l)))]
def info(l): return [dict(t=int(r['epoch_ms']), entries=int(r['entries']), size=int(r['size_bytes']), cap=int(r['capacity_bytes']), hits=int(r['hits']), req=int(r['requests'])) for r in csv.DictReader(open(os.path.join(out, 'info-%s.csv' % l)))]
P = {l: json.load(open(os.path.join(out, 'phase-%s.json' % l))) for l in ('c0', 'c64', 'c256', 'c1024', 'big') if os.path.exists(os.path.join(out, 'phase-%s.json' % l))}
D = {}
for l, S in P.items():
    if l == 'big': continue
    s = samples(l); base = S['baseline_kb']; a = S['marks']['pass1_start']; b = S['marks'].get('shrink_start', S['marks']['pass2_end'] + 8000)
    w = [v for t, v in s if a <= t <= b]; D[l] = (max(w) - base) / 1024
    inf = [r for r in info(l) if a <= r['t'] <= b]
    print('%s: baseline %.1f MiB, D(peak rise) %.1f MiB, info rows %d, max Size %.1f MiB, end Size %.1f MiB entries %d, RefCountedMemory %d, pass1 %s pass2 %s' % (
        l, base / 1024, D[l], len(inf), max(r['size'] for r in inf) / MiB, inf[-1]['size'] / MiB, inf[-1]['entries'], S['refcounted'], S['pass1']['ok'], S['pass2']['ok']))
    chk(l + ' both passes returned every row, no errors', S['pass1']['ok'] == S['pass2']['ok'] == int(os.environ.get('STAGE4_SMALL', 16384)) and S['pass1']['err'] == S['pass2']['err'] == 0, '%s %s' % (S['pass1'], S['pass2']))
    if l == 'c0':
        chk('c0 capacity 0 and < 100 RefCountedMemory', inf[-1]['cap'] == 0 and S['refcounted'] < 100, 'cap %d rc %d' % (inf[-1]['cap'], S['refcounted']))
        continue
    C = S['cap_mib']
    chk('%s Size <= capacity at every sample' % l, all(r['size'] <= r['cap'] for r in inf) and all(r['cap'] == C * MiB for r in inf), 'max %.1f cap %d MiB' % (max(r['size'] for r in inf) / MiB, C))
    chk('%s end Size in [0.95C, C]' % l, 0.95 * C * MiB <= inf[-1]['size'] <= C * MiB, '%.1f MiB' % (inf[-1]['size'] / MiB))
    e = inf[-1]['entries']; chk('%s RefCountedMemory within 5%% of entries' % l, abs(S['refcounted'] - e) <= max(5, 0.05 * e), '%d vs %d' % (S['refcounted'], e))
    chk('%s no OHC/caffinitas classes' % l, not S['ohc_lines'], str(S['ohc_lines']))
    d = D[l] - D['c0']; chk('%s D(C)-D0 in [0.8C, 1.25C+64]' % l, 0.8 * C <= d <= 1.25 * C + 64, '%.1f MiB (C=%d)' % (d, C))
for a, b, dc in (('c64', 'c256', 192), ('c256', 'c1024', 768)):
    if a in D and b in D:
        d = D[b] - D[a]; chk('D(%s)-D(%s) in [0.8,1.25] x %d' % (b, a, dc), 0.8 * dc <= d <= 1.25 * dc, '%.1f' % d)
for l in ('c64', 'c256', 'c1024'):
    if l in D: chk(l + ' D below 2048 MiB (the :94 limit)', D[l] < 2048, '%.1f' % D[l])
if 'c256' in P and 'shrink_polls' in P['c256']:
    S = P['c256']; polls = [p for p in S['shrink_polls'] if p]
    chk('shrink: Size <= 32 MiB within 10 s', any(p['size'] <= 32 * MiB for p in polls[:5]), str([round(p['size'] / MiB, 1) for p in polls]))
    s = samples('c256'); tail = [v for t, v in s if t >= S['marks']['shrink_end'] - 4000]
    r = (sum(tail) / len(tail) - S['baseline_kb']) / 1024 - D['c0']; chk('shrink: RssAnon rise minus D0 <= 104 MiB', r <= 104, '%.1f' % r)
if 'big' in P:
    S = P['big']; s = samples('big'); base = S['baseline_kb']; D0 = D.get('c0', 0)
    pk = lambda a, b: (max(v for t, v in s if a <= t <= b) - base) / 1024
    r8 = [pk(r['a'], r['b'] + 1500) for r in S['big8_rounds']]; ok8 = sum(r['ok'] for r in S['big8_rounds']); er8 = sum(r['err'] for r in S['big8_rounds'])
    r256 = [pk(r['a'], r['b'] + 1500) for r in S['big256_reads']]
    inf = info('big'); print('big: baseline %.1f; big8 round peaks %s; big256 read peaks %s; reads ok8=%d err8=%d; max Size %.1f MiB end entries %d' % (base / 1024, [round(x) for x in r8], [round(x) for x in r256], ok8, er8, max(r['size'] for r in inf) / MiB, inf[-1]['entries']))
    chk('big8 all 160 reads returned, no error', ok8 == 160 and er8 == 0, '%d/%d' % (ok8, er8))
    chk('big8 end Size 0 and entries 0; Size <= capacity at every sample', inf[-1]['size'] == 0 and inf[-1]['entries'] == 0 and all(r['size'] <= r['cap'] for r in inf), 'end %d/%d' % (inf[-1]['size'], inf[-1]['entries']))
    chk('big8 some round peak >= 96 MiB', max(r8) >= 96, '%.1f' % max(r8))
    chk('big256 every read peak >= 200 MiB', len(r256) == 5 and all(x >= 200 for x in r256) and all(r['err'] == 0 for r in S['big256_reads']), str([round(x) for x in r256]))
    end = (sum(v for t, v in s[-100:]) / 100 - base) / 1024
    chk('big256 end rise <= D0+32', end <= D0 + 32, '%.1f vs D0 %.1f' % (end, D0))
for r in R: print(*r, sep=' | ')
print('TOTAL pass=%d fail=%d' % (sum(1 for r in R if r[0] == 'PASS'), sum(1 for r in R if r[0] == 'FAIL')))
