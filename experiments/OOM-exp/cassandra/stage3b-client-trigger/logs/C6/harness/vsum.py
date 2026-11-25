#!/usr/bin/env python3
"""C6 3-b confirm (2026-11-24): vsum.py <run dir>: the victim role's view per phase. Phase boundaries are the t_* marks in
summary.json (victim_start, attack_start/ddl_start, ddl_end, write_start, write_end, daemon_gone, serving, victim_stop),
sorted by time; each phase runs from one mark to the next. Per phase: ticks, OK, success % (missed/down ticks count as
failures), OK latency p50/p99/max, failures by kind. Writes victim-persec.txt (second relative to the first mark after
victim_start: ticks ok fail p50 max)."""
import json, os, re, sys
R = sys.argv[1]
S = json.load(open(os.path.join(R, 'summary.json')))
marks = sorted((v, k[2:]) for k, v in S.items() if k.startswith('t_') and isinstance(v, int) and k not in ('t_launch', 't_jmx_up', 't_ddl_start'))
rows = []
for l in open(os.path.join(R, 'victim.txt'), errors='replace'):
    if l.startswith('#') or not l.strip(): continue
    p = l.split(); rows.append((int(p[0]), p[1], int(p[2]), p[3]))
def pct(v, q):
    v = sorted(v); return v[min(len(v) - 1, int(q * len(v)))] if v else 0
ref = dict((k, v) for v, k in marks).get('attack_start') or dict((k, v) for v, k in marks).get('serving') or marks[0][0]
print('marks (s rel. attack/serving):', ', '.join('%s %+.1f' % (k, (v - ref) / 1000) for v, k in marks))
for i, (t0, name) in enumerate(marks):
    t1 = marks[i + 1][0] if i + 1 < len(marks) else 1 << 62
    rs = [r for r in rows if t0 <= r[0] < t1]
    if not rs: continue
    ok = [r for r in rs if r[3] == 'OK']; lat = [r[2] for r in ok]
    errs = {}
    for r in rs:
        if r[3] != 'OK':
            k = re.sub(r'[0-9]+', 'N', r[3])[:60]; errs[k] = errs.get(k, 0) + 1
    print('from %-13s %7.1f s: ticks %5d OK %5d (%5.1f%%) p50 %d p99 %d max %d ms; fail: %s' % (
        name, (min(t1, rs[-1][0]) - t0) / 1000, len(rs), len(ok), 100.0 * len(ok) / len(rs), pct(lat, .5), pct(lat, .99),
        max(lat) if lat else 0, ', '.join('%s x%d' % kv for kv in sorted(errs.items(), key=lambda x: -x[1])) or 'none'))
after = [r for r in rows if r[0] >= ref]
f = [r for r in after if r[3] != 'OK']; o = [r for r in after if r[3] == 'OK']
if f: print('first failure %+.1f s (%s)' % ((f[0][0] - ref) / 1000, f[0][3][:60]))
if o: print('last OK %+.1f s' % ((o[-1][0] - ref) / 1000))
by = {}
for t, op, lat, st in rows:
    s = (t - ref) // 1000; v = by.setdefault(s, [0, 0, 0, []]); v[0] += 1
    if st == 'OK': v[1] += 1; v[3].append(lat)
    else: v[2] += 1
with open(os.path.join(R, 'victim-persec.txt'), 'w') as fo:
    fo.write('# sec_rel_ref ticks ok fail p50_ms max_ms\n')
    for s in sorted(by):
        v = by[s]; fo.write('%d %d %d %d %d %d\n' % (s, v[0], v[1], v[2], pct(v[3], .5), max(v[3]) if v[3] else 0))
