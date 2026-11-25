#!/usr/bin/env python3
# B28 3-b confirm (2026-11-24): R13 3-b victim_summary.py, phase regex also accepts "attack client ended".
"""R13 3-b confirm (2026-11-23): victim_summary.py <run dir>: the victim role's view before / during / after the attack.
Phases from driver.txt: before = victim start .. attack start; during = attack start .. endpoint (daemon gone) or attack
end (hold); after = from then to victim stop. Per phase: ticks, OK, errors by kind, success rate (OK / ticks, where 'missed'
and 'down' ticks count as failures), OK latency p50 / p99 / max. Writes <run dir>/victim-persec.txt (second relative to
the attack start, ticks, ok, failures, p50 ms, max ms)."""
import os, re, sys
R = sys.argv[1]
drv = open(os.path.join(R, 'driver.txt'), errors='replace').read()
a0 = int(re.search(r'attack start .* at_ms (\d+)', drv).group(1))
m = re.search(r'(daemon gone while attack running|attack clients? ended; daemon alive \(hold end\)) at_ms (\d+)', drv)
a1 = int(m.group(2)) if m else None
kind = ('node died' if m and m.group(1).startswith('daemon gone') else 'attack ended (node alive)') if m else '?'
rows = []
for l in open(os.path.join(R, 'victim.txt'), errors='replace'):
    if l.startswith('#') or not l.strip(): continue
    p = l.split()
    rows.append((int(p[0]), p[1], int(p[2]), p[3]))
def phase(t):
    if t < a0: return 'before'
    if a1 is None or t < a1: return 'during'
    return 'after'
def pct(v, q):
    v = sorted(v); return v[min(len(v) - 1, int(q * len(v)))] if v else 0
print('attack start %d; phase boundary %s (%s, %+.1f s after attack start)' % (a0, a1, kind, (a1 - a0) / 1000 if a1 else float('nan')))
for ph in ('before', 'during', 'after'):
    rs = [r for r in rows if phase(r[0]) == ph]
    if not rs: print('%-6s: no ticks' % ph); continue
    ok = [r for r in rs if r[3] == 'OK']
    errs = {}
    for r in rs:
        if r[3] != 'OK':
            k = re.sub(r'[0-9]+', 'N', r[3])[:70]; errs[k] = errs.get(k, 0) + 1
    span = (rs[-1][0] - rs[0][0]) / 1000
    lat = [r[2] for r in ok]
    print('%-6s: %.1f s, ticks %d, OK %d (%.1f%%), OK latency ms p50 %d p99 %d max %d; failures: %s' % (
        ph, span, len(rs), len(ok), 100.0 * len(ok) / len(rs), pct(lat, .5), pct(lat, .99), max(lat) if lat else 0,
        ', '.join('%s x%d' % kv for kv in sorted(errs.items(), key=lambda x: -x[1])) or 'none'))
# first failure after the attack start and last OK
fail = [r for r in rows if r[0] >= a0 and r[3] != 'OK']
okd = [r for r in rows if r[0] >= a0 and r[3] == 'OK']
if fail: print('first victim failure after attack start: %+.1f s (%s)' % ((fail[0][0] - a0) / 1000, fail[0][3][:60]))
if okd: print('last victim OK after attack start: %+.1f s' % ((okd[-1][0] - a0) / 1000))
slow = [r for r in rows if r[0] >= a0 and r[3] == 'OK' and r[2] > 1000]
if slow: print('OK requests slower than 1 s during/after: %d (max %d ms)' % (len(slow), max(r[2] for r in slow)))
by = {}
for t, op, lat, st in rows:
    s = (t - a0) // 1000
    v = by.setdefault(s, [0, 0, 0, []]); v[0] += 1
    if st == 'OK': v[1] += 1; v[3].append(lat)
    else: v[2] += 1
with open(os.path.join(R, 'victim-persec.txt'), 'w') as f:
    f.write('# sec_rel_attack ticks ok fail p50_ms max_ms\n')
    for s in sorted(by):
        v = by[s]; f.write('%d %d %d %d %d %d\n' % (s, v[0], v[1], v[2], pct(v[3], .5), max(v[3]) if v[3] else 0))
