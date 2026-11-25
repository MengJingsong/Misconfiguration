#!/usr/bin/env python3
"""o127 analyzer: B2f/B2g and B3f/B3g checks with the S4-A4/S4-A5 thresholds, from the raw files.
Usage: analyze.py <run1-dir>   (expects <run1>/unit/run1/run-*.log and <run1>/cluster/<label>/session.txt)"""
import glob, os, re, sys
R = sys.argv[1]
out = []
def p(*a): out.append(' '.join(str(x) for x in a))

# ---------------- unit ----------------
U = {}
for f in sorted(glob.glob(os.path.join(R, 'unit', 'run1', 'run-*.log'))):
    lab = os.path.basename(f)[4:-4]
    d = {'cp': [], 'final': None, 'hdr': None}
    for l in open(f):
        if not l.startswith('READING '): continue
        m = re.search(r'O127 cap=(\S+) m=(\d+) len=(\d+) i=0 size=(\d+) deep=(\d+)', l)
        if m: d['hdr'] = dict(cap=m.group(1), m=int(m.group(2)), len=int(m.group(3)), B0=int(m.group(5))); continue
        m = re.search(r'O127 i=(\d+) size=(\d+) deep=(\d+)', l)
        if m: d['cp'].append(tuple(int(x) for x in m.groups())); continue
        m = re.search(r'O127 FINAL size=(\d+) present=(\d+) presentInLastN=(\d+) deep=(\d+)', l)
        if m: d['final'] = tuple(int(x) for x in m.groups())
    U[lab] = d
p('== UNIT (B2) ==')
ok = True
def mb(x): return '%.3f MB' % (x / 1e6)
exp_n = {'N0': 0, 'N1': 1, 'N1000': 1000, 'N10000': 10000, 'Ndef': 100000, 'N1000-L100': 1000, 'N1000-L10000': 1000}
dB = {}
for lab, N in exp_n.items():
    d = U.get(lab)
    if not d or not d['final'] or not d['hdr']:
        p(lab, 'MISSING'); ok = False; continue
    size, present, lastn, deep = d['final']; B0 = d['hdr']['B0']
    want = min(N, d['hdr']['m'])
    echo_ok = d['hdr']['cap'] == ('default' if lab == 'Ndef' else str(N))
    over = [c for c in d['cp'] if c[1] > N]
    dB[lab] = deep - B0
    flat = ''
    if N in (1000, 10000):
        first = next(c for c in d['cp'] if c[0] >= 2 * N)
        rel = (deep - first[2]) / first[2]
        flat = ' flat: final vs i=%d %+.2f%%%s' % (first[0], 100 * rel, '' if abs(rel) <= 0.10 else ' NOT FLAT')
        if abs(rel) > 0.10: ok = False
    good = size == want and present == want and echo_ok and not over
    if not good: ok = False
    p('%-13s cap=%-7s final size=%d present=%d (want %d) lastN=%d deep-B0=%s checkpoints>N=%d echo=%s%s -> %s' % (
        lab, d['hdr']['cap'], size, present, want, lastn, mb(deep - B0), len(over), echo_ok, flat, 'ok' if good else 'FAIL'))
ctl = dB['Ndef'] / dB['N10000']
p('positive control: (Ndef deep-B0)/(N10000 deep-B0) = %.2f (need >= 4) -> %s' % (ctl, 'ok' if ctl >= 4 else 'FAIL'))
if ctl < 4: ok = False
ratio = dB['N1000-L10000'] / dB['N1000-L100']
p('count-not-bytes: (L10000)/(L100) at N=1000 = %.2f (confirm in [20,50]) -> %s' % (ratio, 'ok' if 20 <= ratio <= 50 else 'NO'))
ranges = {'N1000': (1.1e6, 1.4e6), 'N10000': (11e6, 14e6), 'Ndef': (55e6, 70e6), 'N1000-L100': (0.20e6, 0.38e6), 'N1000-L10000': (7.1e6, 13.3e6)}
for k, (lo, hi) in ranges.items():
    p('  model range %-13s %s in [%s, %s] -> %s' % (k, mb(dB[k]), mb(lo), mb(hi), 'in' if lo <= dB[k] <= hi else 'OUT'))
for k in ('N1000', 'N10000'):
    s, pr, ln, _ = U[k]['final']; p('  presentInLastN %s: %d / %d = %.3f (>= 0.9 informational)' % (k, ln, pr, ln / pr))
p('  per-entry deep (len=1000): N1000 %.0f B, N10000 %.0f B, Ndef %.0f B' % (dB['N1000'] / 1000, dB['N10000'] / 10000, dB['Ndef'] / 50000))
p('UNIT ROW 1 (Confirmed - caps):', 'HOLDS' if ok else 'DOES NOT HOLD')
nneg = os.path.join(R, 'unit', 'run1', 'TEST-Nneg.xml')
if os.path.exists(nneg):
    t = open(nneg).read(); m = re.search(r'Caused by: ([\w.$]+: [^\n]*)', t); e = re.search(r'<error type="([^"]+)"', t)
    p('N=-1:', e.group(1) if e else 'no error', '/', m.group(1) if m else '')

# ---------------- cluster ----------------
p('\n== CLUSTER (B3) ==')
C = {}
for lab in ('N100', 'N10000', 'Ndef'):
    f = os.path.join(R, 'cluster', lab, 'session.txt')
    if not os.path.exists(f): p(lab, 'MISSING'); continue
    t = open(f).read(); d = {}
    for m in re.finditer(r'SAMPLE \S+ phase=(\S+) total=(\d+) byteArr=(\d+) sawEntries=(\d+) notifications=(\d+) heap_info_used (\d+)K', t):
        d[m.group(1)] = dict(total=int(m.group(2)), ba=int(m.group(3)), ent=int(m.group(4)), noti=int(m.group(5)), used=int(m.group(6)) * 1024)
    m = re.search(r'COUNT present=(\d+) completed=(\d+) in_progress=(\d+) failed=(\d+)', t); d['count'] = tuple(int(x) for x in m.groups()) if m else None
    m = re.search(r'PROBE cmd=(\d+) status=(\S+) parts=(\d+) msg_len=(\d+)', t); d['probe'] = (int(m.group(1)), m.group(2), int(m.group(4))) if m else None
    m = re.search(r'DRIVE done issued=(\d+) lastCmd=(\d+) fallbacks=(\d+) t_ms=(\d+)', t); d['drive'] = tuple(int(x) for x in m.groups()) if m else None
    d['cmd0'] = 'cmd 0' in t
    m = re.search(r'ERROR lines: (\d+)', t); d['err'] = int(m.group(1)) if m else None
    C[lab] = d
cok = True
N = {'N100': 100, 'N10000': 10000, 'Ndef': 100000}
for lab, d in C.items():
    b, a, a60 = d['base'], d['after'], d['after60']
    dT = a['total'] - b['total']; dT60 = a60['total'] - b['total']
    want = min(N[lab], 30000)
    stab = abs(a60['total'] - a['total']) / a['total']
    d['dT'] = dT
    p('%-6s drive=%s probe=%s count=%s want present=%d | base %.1f MB, after %.1f MB, after60 %.1f MB | dTotal %s (after60 %s) d[B %s | entries(after) %d | notifications %d | after/after60 diff %.1f%% | ERROR lines %s' % (
        lab, d['drive'], d['probe'], d['count'], want, b['total'] / 1e6, a['total'] / 1e6, a60['total'] / 1e6, mb(dT), mb(dT60), mb(a['ba'] - b['ba']), a['ent'], a['noti'], 100 * stab, d['err']))
    if not d['count'] or d['count'][0] != want: cok = False; p('  present != want')
    if stab > 0.10: cok = False; p('  after vs after60 > 10%')
if all(k in C for k in N):
    e0 = C['Ndef']['probe'][2]
    p('e0 (msg_len) = %d; e0+200 = %d B' % (e0, e0 + 200))
    r = C['Ndef']['dT'] / C['N10000']['dT']
    p('ratio dTotal(def)/dTotal(10000) = %.2f (need [2.4, 3.6]) -> %s' % (r, 'ok' if 2.4 <= r <= 3.6 else 'FAIL'))
    if not 2.4 <= r <= 3.6: cok = False
    p('dTotal(N100) = %s (need < 30 MB) -> %s' % (mb(C['N100']['dT']), 'ok' if C['N100']['dT'] < 30e6 else 'FAIL'))
    if C['N100']['dT'] >= 30e6: cok = False
    es = {}
    for k in ('N10000', 'Ndef'):
        es[k] = C[k]['dT'] / C[k]['count'][0]
        lo, hi = 0.8 * (e0 + 200), 1.4 * (e0 + 200)
        p('e(%s) = %.0f B per entry (need [%.0f, %.0f]) -> %s' % (k, es[k], lo, hi, 'ok' if lo <= es[k] <= hi else 'FAIL'))
        if not lo <= es[k] <= hi: cok = False
    q = es['Ndef'] / es['N10000']; p('e ratio def/10000 = %.2f (need [0.75, 1.25]) -> %s' % (q, 'ok' if 0.75 <= q <= 1.25 else 'FAIL'))
    if not 0.75 <= q <= 1.25: cok = False
    # incremental e from N100 -> N10000 (removes the constant one-time rise)
    inc = (C['N10000']['dT'] - C['N100']['dT']) / (10000 - 100); inc2 = (C['Ndef']['dT'] - C['N10000']['dT']) / (30000 - 10000)
    p('incremental e: N100->N10000 %.0f B, N10000->def %.0f B' % (inc, inc2))
    for k, (lo, hi) in {'N10000': (100e6, 140e6), 'Ndef': (300e6, 400e6)}.items():
        p('  B3f model range %s: %s in [%s, %s] -> %s' % (k, mb(C[k]['dT']), mb(lo), mb(hi), 'in' if lo <= C[k]['dT'] <= hi else 'OUT'))
    inval = C['Ndef']['dT'] < 100e6 or C['Ndef']['count'][0] < 29000 or any(C[k]['cmd0'] for k in C) or e0 < 1000
    p('Invalid conditions:', 'MET' if inval else 'none')
    ref = any(C[k]['count'][0] > N[k] for k in C) or C['N10000']['dT'] >= 0.8 * C['Ndef']['dT'] or C['N100']['dT'] >= 0.5 * C['Ndef']['dT']
    p('Row 2 (Refuted) conditions:', 'MET' if ref else 'none')
    p('CLUSTER ROW 1 (Confirmed - caps):', 'HOLDS' if cok and not inval and not ref else 'DOES NOT HOLD')
print('\n'.join(out))
