#!/usr/bin/env python3 -I
"""Independent self-check (results §5): re-parses the raw files without importing the analysers; the unit expectations come from a
pure-Python re-implementation of Stack.add/resize/refill/splice (Stack.java:60-101), not from the closed forms of the analyser.
Usage: selfcheck.py <run1-dir>   (contains unit-plain/raw, unit-bm/raw, cluster/)"""
import sys, os, re, csv, json, glob
base = sys.argv[1]; ok_all = []
def chk(name, ok, detail=''):
    ok_all.append(ok); print(('HOLDS   ' if ok else 'FAILS   ') + name + ('  | ' + detail if detail else ''))
class Arr:  # a Java array: identity + length
    def __init__(s, n): s.n = n
class Stk:
    def __init__(s): s.stack = Arr(0); s.length = 0; s.mc = Arr(0); s.mcn = 0
    def add_t(s):
        if s.length == s.stack.n: s.stack = Arr(5 if s.stack.n == 0 else s.stack.n * 2)
        s.length += 1
    def add_more(s): s.mc = Arr(s.mc.n + 1); s.holders = getattr(s, 'holders', []) + [s.length]
def splice(prefixCount, keep, keepFrom, keepTo):
    newCount = prefixCount + (keepTo - keepFrom)
    if newCount > keep.n: return Arr(newCount), True
    return keep, False
def simulate(K, M, P, Q, R):
    s = Stk()
    for _ in range(K): s.add_t()
    s.add_more(); holder = K; mclen = s.mc.n
    for _ in range(M): s.add_t()
    stack_changes = mc_changes = splices = grows = 0
    for _ in range(R):
        # replacement contents: Q holders, P transformations; its own arrays
        prefix_stack_len, prefix_mc_len = P, Q
        # moreContents splice (index = position of this holder: Q after the first refill, 0 before it; keep [index, len))
        index = 0 if s.mc.n == 1 and not getattr(s, 'refilled', False) else Q
        s.mc, g1 = splice(prefix_mc_len, s.mc, index, s.mc.n if not getattr(s, 'refilled', False) else s.mc.n)
        s.stack, g2 = splice(prefix_stack_len, s.stack, holder, s.length)
        splices += 2; grows += int(g1) + int(g2); stack_changes += int(g2); mc_changes += int(g1)
        s.length += P - holder; holder = P; s.refilled = True
    return s.stack.n, s.length, stack_changes, mc_changes, splices, grows, s.mc.n
# ---- unit ----
raw = os.path.join(base, 'unit-plain/raw/raw.csv')
rows = [l.strip().split(',') for l in open(raw) if l.strip() and not l.startswith('#')]
bad = []
n_ref = 0
for r in rows:
    if r[0] == 'buildup':
        s = Stk()
        for _ in range(int(r[1])): s.add_t()
        if (s.stack.n, s.length) != (int(r[6]), int(r[7])): bad.append(r)
    elif r[0] == 'refill':
        k, m, p, q, rr = map(int, r[1:6]); n_ref += 1
        sl, ln, sc_, mc_, spl, gr, mcn = simulate(k, m, p, q, rr)
        if (sl, ln, sc_, mc_, mcn, spl) != (int(r[9]), int(r[10]), int(r[13]), int(r[14]), int(r[11]), 2 * int(r[12])): bad.append(('mismatch', r, (sl, ln, sc_, mc_, mcn, spl)))
chk('unit: %d buildup+refill rows equal an independent re-implementation of Stack.add/splice' % len(rows), not bad, str(bad[:2]))
tot = [l for l in open(raw) if l.startswith('# TOTAL')][0]
# totals: recompute from the rows
refills = sum(int(r[12]) for r in rows if r[0] == 'refill'); sch = sum(int(r[13]) for r in rows if r[0] == 'refill'); mch = sum(int(r[14]) for r in rows if r[0] == 'refill')
chk('unit: footer totals equal totals recomputed from the rows', 'refills=%d stackChanges=%d mcChanges=%d' % (refills, sch, mch) in tot, tot.strip())
bmraw = os.path.join(base, 'unit-bm/raw'); S = G = other = 0
for l in open(os.path.join(bmraw, 'trace.txt')):
    t = l.split()[0] if l.strip() else ''
    if t == 'S': S += 1
    elif t == 'G': G += 1
    else: other += 1
bmrows = [l.strip().split(',') for l in open(os.path.join(bmraw, 'raw.csv')) if l.strip() and not l.startswith('#')]
bmref = sum(int(r[12]) for r in bmrows if r[0] == 'refill'); bmg = sum(int(r[13]) + int(r[14]) for r in bmrows if r[0] == 'refill')
chk('unit (Byteman JVM): S lines %d == 2 x refills %d; G lines %d == identity changes %d; no other trace lines (%d)' % (S, bmref, G, bmg, other), S == 2 * bmref and G == bmg and other == 0)
chk('unit: the Byteman JVM raw rows equal the plain JVM raw rows for the shared arms', [r for r in rows if r[0] in ('buildup', 'refill')] == bmrows)
# U4/U5 raw facts
hs = [r for r in rows if r[0] == 'heapstack']; ctl = [r for r in rows if r[0] == 'control']
chk('unit: heap arm: iterator delta / Object[] delta within [0.8,1.25] in all %d repetitions' % len(hs), all(0.8 <= int(r[4]) / int(r[5]) <= 1.25 for r in hs), str([(r[4], r[5]) for r in hs]))
chk('unit: control N arms: heap delta rises with N, each in [0.9,2.0] x N KiB, stack.length 6', all(0.9 * int(r[2]) * 1024 <= int(r[5]) <= 2.0 * int(r[2]) * 1024 and r[6] == '6' for r in ctl if r[1] != 'ctl_cap') and [int(r[5]) for r in ctl if r[1] != 'ctl_cap'] == sorted(int(r[5]) for r in ctl if r[1] != 'ctl_cap'), str([(r[1], r[3], r[5], r[6]) for r in ctl]))
cap = [r for r in ctl if r[1] == 'ctl_cap'][0]
chk('unit: ctl_cap hit OutOfMemoryError at Xmx512m with %s rows held (%.0f MiB), stack.length %s' % (cap[3], int(cap[3]) * 1024 / 2**20, cap[6]), cap[4] == 'true' and cap[7] == str(512 * 2**20) and cap[6] == '5')
# ---- cluster ----
cl = os.path.join(base, 'cluster'); R = json.load(open(os.path.join(cl, 'phases.json')))
for n in '12':
    S = G = SRP = 0; mx = 0
    for l in open(os.path.join(cl, 'node%s-byteman-trace.txt' % n)):
        f = l.split()
        if not f: continue
        if f[0] == 'S': S += 1; mx = max(mx, int(f[1]))
        elif f[0] == 'G': G += 1
        elif f[0] == 'SRP': SRP += 1
    srp_log = sum(1 for l in open(os.path.join(cl, 'node%s-system.log' % n), errors='replace') if 'for short read protection' in l)
    print('INFO    node%s whole-run trace: S=%d G=%d SRP-rule=%d, system.log short-read lines=%d, largest newCount=%d' % (n, S, G, SRP, srp_log, mx))
    chk('cluster node%s: G == 0 over the whole run (every Byteman line re-counted)' % n, G == 0)
    if n == '1': chk('cluster node1: SRP rule hits == "short read protection" log lines, and S == 2 x ... (S counts every splice, not only SRP)', SRP == srp_log and S >= 2 * SRP, 'SRP=%d log=%d S=%d' % (SRP, srp_log, S))
for k, v in sorted(R['scan'].items()):
    rows_ = list(csv.DictReader(open(os.path.join(cl, 'samples-%s.csv' % k))))
    inside = [r for r in rows_ if v['t_start'] <= int(r['t_ms']) <= v['t_end']]
    arr = max(sum(int(r[c]) for c in r if c.endswith('_bytes') and ('transform' in c)) for r in rows_)
    tot1 = max(int(r['total_bytes']) for r in rows_ if r['node'] == '1'); idle1 = min(int(r['total_bytes']) for r in rows_ if r['node'] == '1')
    print('INFO    %s: %d samples (%d inside the scan window), nscans=%d rows/scan=%s, max array bytes=%d, node1 live total min=%.1f MiB max=%.1f MiB' % (k, len(rows_), len(inside), v['nscans'], v['rows_per_scan'], arr, idle1 / 2**20, tot1 / 2**20))
    chk('cluster %s: >= 10 samples inside the scan window and every scan returned min(L, 40000) rows' % k, len(inside) >= 10 and v['rows_per_scan'] == [min(v['L'], 40000)])
kc = R['control']
def entries(s): return int(re.search(r'entries (\d+)', s).group(1))
chk('cluster control: nodetool info key cache entries 0 with capacity 0, then >= 40000 with capacity 64 MiB', entries(kc['keycache_off']['key_cache_line']) == 0 and entries(kc['keycache_64']['key_cache_line']) >= 40000, kc['keycache_off']['key_cache_line'][:80] + ' | ' + kc['keycache_64']['key_cache_line'][:90])
print('SELFCHECK %d HOLD, %d FAIL' % (sum(ok_all), len(ok_all) - sum(ok_all)))
