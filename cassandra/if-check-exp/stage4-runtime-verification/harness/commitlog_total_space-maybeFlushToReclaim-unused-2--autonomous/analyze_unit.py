#!/usr/bin/env python3
"""Unit-tier analysis for commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous (B2f/B2g as amended R3; B2i R5, H1).
Usage: python3 -I analyze_unit.py <run1/unit dir>
Reads only raw files: each arm's cap.csv (1-ms sampler), cap.csv.summary, cap.csv.trace (Byteman), ant.log, and the raw
test-log tree testlogs/ (plain or .gz, opened by magic bytes) for the flush census. Does not read reasons.txt."""
import gzip, os, re, sys

MiB = 1 << 20
S = 1 * MiB
D = sys.argv[1]
ok_n = [0, 0]

def exp(desc, cond):
    ok_n[0 if cond else 1] += 1
    print(f"EXPECTED: {desc}: {'yes' if cond else 'NO'}")

def csv(arm):
    rows = []
    with open(os.path.join(D, arm, 'cap.csv')) as f:
        hdr = None
        for line in f:
            p = line.strip().split(',')
            if p[0] == 'tMs':
                hdr = p; continue
            if len(p) != 6: continue
            rows.append(dict(t=int(p[0]), phase=p[1], sz=int(p[2]), act=int(p[3]), d=int(p[4]), sw=int(p[5])))
    return rows

def summary(arm):
    s = {}
    for line in open(os.path.join(D, arm, 'cap.csv.summary')):
        for k, v in re.findall(r'(\w+)=(\S+)', line):
            s[k] = v
    return s

def testlog(arm):
    out = []
    root = os.path.join(D, arm, 'testlogs')
    for dp, _, fs in os.walk(root):
        for fn in sorted(fs):
            p = os.path.join(dp, fn)
            with open(p, 'rb') as f:
                magic = f.read(2)
            op = gzip.open if magic == b'\x1f\x8b' else open
            with op(p, 'rt', errors='replace') as f:
                out.extend(f.readlines())
    return out

def census(arm):
    c = {}
    for l in testlog(arm):
        m = re.search(r'Enqueuing flush of (CLCap\.\w+), Reason: (\w+)', l)
        if m:
            c[m.group(2)] = c.get(m.group(2), 0) + 1
    return c

def trace(arm):
    ev = []
    p = os.path.join(D, arm, 'cap.csv.trace')
    if not os.path.exists(p): return ev
    for line in open(p):
        kind = line.split()[0]
        d = dict(re.findall(r'(\w+)=(\S+)', line)); d['kind'] = kind
        ev.append(d)
    return ev

def ant_ok(arm):
    t = open(os.path.join(D, arm, 'ant.log')).read()
    return 'Tests run: 1, Failures: 0, Errors: 0' in t and 'BUILD SUCCESSFUL' in t

R = {}
for arm in ['T3-s20', 'T4-s20', 'T8-s20', 'T1024-s20', 'T4-s0', 'T1024-s0', 'M', 'M-nobreak']:
    rows = csv(arm); s = summary(arm); c = census(arm)
    w = [r for r in rows if r['phase'] == 'write']
    st = [r for r in rows if r['phase'] == 'settle']
    peak = max(r['sz'] for r in rows); peakd = max(r['d'] for r in rows)
    settled = int(s['settledOnDisk']); settledd = int(s['settledDir'])
    falls = sum(1 for a, b in zip(rows, rows[1:]) if b['sz'] < a['sz'])
    mono = all(b['sz'] >= a['sz'] for a, b in zip(w, w[1:]))
    maxdiff = max(abs(r['d'] - r['sz']) for r in rows)
    R[arm] = dict(rows=rows, w=w, peak=peak, peakd=peakd, settled=settled, settledd=settledd, c=c, falls=falls, mono=mono,
                  ev=trace(arm), info=s, maxdiff=maxdiff)
    print(f"ARM {arm}: ant_ok={ant_ok(arm)} samples={len(rows)} (write {len(w)}, settle {len(st)}) T={s['totalMiB']} sleep={s['sleepMs']} "
          f"mode={s['mode']} nobreak={s['nobreak']} segMiB={s['segMiB']} accessMode={s['accessMode']} heapMaxMiB={s['heapMaxMiB']} "
          f"memtableHeapMiB={s['memtableHeapMiB']} | peak={peak/MiB:.0f}MiB peakDir={peakd/MiB:.0f} settled={settled/MiB:.0f} "
          f"settledDir={settledd/MiB:.0f} switches={s['switches']} falls={falls} writeMonotone={mono} max|dir-counter|={maxdiff/MiB:.0f}MiB "
          f"census={c} trace CHECK={sum(e['kind']=='CHECK' for e in R[arm]['ev'])} SELECT={sum(e['kind']=='SELECT' for e in R[arm]['ev'])}")

print("\n== B2f (S = 1 MiB, 20 ms)")
ctrl = R['T1024-s20']['peak']
for T, arm, lo in [(3, 'T3-s20', 4), (4, 'T4-s20', 4), (8, 'T8-s20', 2)]:
    a = R[arm]
    exp(f"{arm} peak {a['peak']/MiB:.0f} <= T+2S = {T+2} MiB", a['peak'] <= (T + 2) * MiB)
    exp(f"{arm} settled {a['settled']/MiB:.0f} <= T = {T} MiB", a['settled'] <= T * MiB)
    exp(f"{arm} COMMITLOG_DIRTY {a['c'].get('COMMITLOG_DIRTY',0)} >= {lo}", a['c'].get('COMMITLOG_DIRTY', 0) >= lo)
    exp(f"{arm} file-length sum within 1 segment of onDiskSize (max diff {a['maxdiff']/MiB:.0f} MiB)", a['maxdiff'] <= S)
a = R['T1024-s20']
exp(f"control peak {a['peak']/MiB:.0f} MiB in 17-18 MiB", 17 * MiB <= a['peak'] <= 18 * MiB)
exp(f"control rises monotonically in write phase", a['mono'])
exp(f"control settled = peak ({a['settled']/MiB:.0f})", a['settled'] == a['peak'])
exp(f"control COMMITLOG_DIRTY 0 ({a['c'].get('COMMITLOG_DIRTY',0)})", a['c'].get('COMMITLOG_DIRTY', 0) == 0)
ov = [R[x]['peak'] / MiB - T for x, T in [('T3-s20', 3), ('T4-s20', 4), ('T8-s20', 8)]]
exp(f"peak - T roughly the same across 3,4,8: {ov}", max(ov) - min(ov) <= 1)
a = R['T4-s0']
exp(f"unthrottled T=4 peak {a['peak']/MiB:.0f} <= T+4S = 8 MiB", a['peak'] <= 8 * MiB)
exp(f"unthrottled T=4 settled {a['settled']/MiB:.0f} <= 4 MiB", a['settled'] <= 4 * MiB)
a = R['T1024-s0']
print(f"INFO unthrottled control peak {a['peak']/MiB:.0f} MiB, COMMITLOG_DIRTY {a['c'].get('COMMITLOG_DIRTY',0)}")

print("\n== B2g rows (R3), in order")
binding = [('T3-s20', 3), ('T4-s20', 4), ('T8-s20', 8)]
peaks = [R[x]['peak'] for x, _ in binding]
follows = peaks == sorted(peaks) and all(p < 0.8 * ctrl for p in peaks)
print(f"peaks {[p/MiB for p in peaks]} MiB, control {ctrl/MiB:.0f}, 0.8*control {0.8*ctrl/MiB:.1f}; peak follows T: {follows}")
anymem = any(R[x]['c'].get('MEMTABLE_LIMIT', 0) + R[x]['c'].get('MEMTABLE_PERIOD_EXPIRED', 0) for x in R)
row = None
if ctrl <= 8 * MiB: row = '5 Invalid'
elif anymem: row = '6 Invalid'
elif any(R[x]['peakd'] > R[x]['peak'] + 2 * S or (R[x]['settledd'] > (T + 1) * MiB and R[x]['settled'] <= T * MiB) for x, T in binding): row = '7 Refuted for disk'
elif any(p >= 0.8 * ctrl for p in peaks): row = '2 Refuted'
elif any(R[x]['c'].get('COMMITLOG_DIRTY', 0) > 0 and R[x]['settled'] > (T + 1) * MiB for x, T in binding): row = '3 Refuted'
elif follows and any(R[x]['c'].get('COMMITLOG_DIRTY', 0) == 0 for x, _ in binding): row = '8 Not confirmed'
else:
    base = follows and all(R[x]['settled'] <= T * MiB and R[x]['c'].get('COMMITLOG_DIRTY', 0) >= 1 for x, T in binding) \
           and R['T1024-s20']['c'].get('COMMITLOG_DIRTY', 0) == 0
    strict = base and all(R[x]['peak'] <= (T + 2) * MiB for x, T in binding) and max(ov) - min(ov) <= 1 and R['T4-s0']['peak'] <= 8 * MiB
    row = '1 Confirmed' if strict else ('4 Confirmed (missed sub-predictions)' if base else 'no row')
print(f"UNIT B2g ROW: {row}")

print("\n== B2i (line 259)")
def troughs(arm):
    a = R[arm]; ev = a['ev']
    sel = [e for e in ev if e['kind'] == 'SELECT']
    if not sel: return None, None
    t0 = int(sel[0]['tMs'])
    after = [r for r in a['w'] if r['t'] >= t0]
    return (min(r['sz'] for r in after) if after else None), sel
for arm in ['M', 'M-nobreak']:
    tr, sel = troughs(arm)
    ev = R[arm]['ev']
    per = {}
    for e in ev:
        if e['kind'] == 'FLUSH' and e['table'].startswith('CLCap.M') and e['switch'] == 'true':
            per[int(e['sel'])] = per.get(int(e['sel']), 0) + 1
    print(f"{arm}: SELECT events {len(sel)}; trough after first SELECT (write phase) {tr/MiB:.0f} MiB; settled {R[arm]['settled']/MiB:.0f} MiB; "
          f"peak {R[arm]['peak']/MiB:.0f} MiB; switching M* tables per SELECT {per}")
    for e in sel:
        print(f"  SELECT {e['n']}: unused={int(e['unused'])/MiB:.0f}MiB sel={int(e['sel'])/MiB:.0f}MiB k={e['k']} gap={e['gap']} "
              f"stop259={e['stop259']} minimal={e['minimal']} concurrentSwitch={e['allocId'] != e['allocIdAtCheck']}")
    R[arm]['sel'] = sel; R[arm]['tr'] = tr; R[arm]['per'] = per

M, NB = R['M'], R['M-nobreak']
T = 8
clean = [e for e in M['sel'] if e['allocId'] == e['allocIdAtCheck']]
p1 = len(M['sel']) >= 4
p2a = all((e['stop259'] == 'true' and e['minimal'] == 'true') or e['gap'] == '0' for e in clean)
p2b = any(e['stop259'] == 'true' and int(e['gap']) > 0 for e in clean)
p3 = all(M['per'].get(int(e['n']), 0) <= int(e['k']) + 1 for e in M['sel'])
p4a = M['tr'] >= (T - 3) * MiB
p4b = (T - 3) * MiB <= M['settled'] <= T * MiB
exp(f"M P1 >= 4 SELECT events ({len(M['sel'])})", p1)
exp(f"M P2 every SELECT stop259&minimal or gap=0 ({len(clean)} without concurrent switch)", p2a)
exp(f"M P2 >= 1 SELECT with stop259 and gap>0", p2b)
exp(f"M P3 switching M* tables per SELECT <= k+1 ({M['per']})", p3)
exp(f"M P4 trough {M['tr']/MiB:.0f} MiB >= T-3S = 5 MiB", p4a)
exp(f"M P4 settled {M['settled']/MiB:.0f} MiB in [5, 8]", p4b)
nb1 = all(e['gap'] == '0' for e in NB['sel'])
nb2 = any(v >= 3 for v in NB['per'].values())
nb3 = NB['tr'] <= 3 * MiB
nb4 = NB['peak'] <= (T + 2) * MiB
exp(f"M-nobreak every SELECT gap=0", nb1)
exp(f"M-nobreak >= 1 SELECT switching >= 3 M* tables ({NB['per']})", nb2)
exp(f"M-nobreak trough {NB['tr']/MiB:.0f} MiB <= 3S", nb3)
exp(f"M-nobreak peak {NB['peak']/MiB:.0f} <= T+2S", nb4)
# rows i1..i6 in order
if len(M['sel']) < 2: irow = 'i1 Invalid'
elif not nb1 or NB['tr'] > 3 * MiB: irow = 'i2 Invalid'
elif any(int(e['gap']) > 0 and (e['minimal'] != 'true' or e['stop259'] != 'true') for e in clean): irow = 'i3 Refuted'
elif p1 and p2a and M['tr'] <= 3 * MiB: irow = 'i4 Not confirmed'
elif p1 and p2a and p2b and p3 and p4a and p4b and nb1 and nb2 and nb3 and nb4: irow = 'i5 Confirmed'
elif p1 and p2a and p2b and p4a: irow = 'i6 Confirmed (missed sub-prediction)'
else: irow = 'no row'
print(f"UNIT B2i ROW: {irow}")
print(f"\nTOTAL EXPECTED yes={ok_n[0]} NO={ok_n[1]}")
