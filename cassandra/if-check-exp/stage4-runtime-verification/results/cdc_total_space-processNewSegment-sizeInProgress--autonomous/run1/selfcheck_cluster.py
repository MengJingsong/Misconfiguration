#!/usr/bin/env python3 -I
"""Independent re-parse of the committed cluster excerpts (cluster/<cell>/...) against every sub-prediction of the frozen B3f / B3g.
Prints PASS / MISS per sub-prediction and a per-cell reading table. usage: selfcheck_cluster.py <run1 dir>"""
import os, re, sys
MIB = 1 << 20; S = 32 * MIB; IDX = 4096
base = os.path.join(sys.argv[1], 'cluster')
def num(pat, text, default=None):
    m = re.search(pat, text); return int(m.group(1).replace(',', '')) if m else default
cells = {}
for name in sorted(os.listdir(base)):
    d = os.path.join(base, name)
    if not os.path.isdir(d) or not os.path.exists(d + '/phases.csv'): continue
    c = {'name': name}
    summ = open(d + '/summary.txt').read()
    ph = {}
    for l in open(d + '/phases.csv'):
        t, lab = l.strip().split(',', 1)
        ph.setdefault(lab, []).append(int(t))
    steps = []
    for l in open(d + '/sampler-changes.csv').read().splitlines()[1:]:
        f = l.split(','); steps.append((int(f[0]), int(f[2]), int(f[1])))
    def at(t):
        v = (0, 0)
        for (ts, b, n) in steps:
            if ts <= t: v = (b, n)
            else: break
        return v
    def window(a, b):  # time-weighted values of (bytes, links) on [a, b]
        pts = [(a,) + at(a)] + [(ts, bb, nn) for (ts, bb, nn) in steps if a < ts < b] + [(b, 0, 0)]
        out = []
        for i in range(len(pts) - 1): out.append((pts[i][1], pts[i][2], pts[i + 1][0] - pts[i][0]))
        return out
    def wmedian(vals):  # vals: (value, weight)
        vals = sorted(vals); tot = sum(w for _, w in vals); acc = 0
        for v, w in vals:
            acc += w
            if acc >= tot / 2: return v
    we, ws = ph['W_end'][0], ph['W_start'][0]
    w60 = window(we - 60000, we)
    c['steadyBytes'] = wmedian([(b, w) for b, n, w in w60]); c['steadyLinks'] = wmedian([(n, w) for b, n, w in w60])
    wall = window(ws, ph['W_plus30'][0] + 3000)
    c['Wpeak'] = max(b for b, n, w in wall); c['Wpeakl'] = max(n for b, n, w in wall)
    c['atWend'] = at(we)[0]; c['atWend60'] = at(we - 60000)[0]
    c['finalBytes'], c['finalLinks'] = at(ph['W_plus30'][0] + 3000)
    c['errors'] = num(r'Total errors\s*:\s*([\d,]+)', summ, -1)
    tr = re.search(r'traces: (.*)', summ).group(1)
    for k in ('created', 'forbidden', 'deleteOld', 'rejectLines', 'WARN', 'FreedUp', 'ERROR'): c[k] = num(k + r'=(\d+)', tr, -1)
    m = re.search(r'release: accepted=(\d) after (\d+) probe\(s\), (\d+) ms', summ)
    c['release'] = (int(m.group(1)), int(m.group(3))) if m else None
    c['settings'] = open(d + '/settings.txt').read()
    cells[name] = c
out = []
def chk(ok, text): out.append(('PASS ' if ok else 'MISS ') + text)
def g(n): return cells.get(n)
print('| cell | W peak MiB | steady median MiB (last 60 s of W) | steady links | final MiB / links (W+30 s) | stress errors | WARN Rejecting | forbidden segs | deleteOld | Freed up | release |')
print('|---|---|---|---|---|---|---|---|---|---|---|')
for n, c in cells.items():
    print('| %s | %.1f | %.1f | %s | %.1f / %d | %d | %d | %d | %d | %d | %s |' % (n, c['Wpeak'] / MIB, c['steadyBytes'] / MIB, c['steadyLinks'], c['finalBytes'] / MIB, c['finalLinks'], c['errors'], c['WARN'], c['forbidden'], c['deleteOld'], c['FreedUp'], c['release']))
print()
for n, c in cells.items():
    head = n.rsplit('-r', 1)[0]; cap = int(re.sub(r'\D', '', head))
    for k, v in (('cdc_total_space', '%dMiB' % cap),):
        chk(re.search(r'cdc_total_space\s*\|\s*%s' % v, c['settings']) is not None, '%s setting read-back cdc_total_space = %s' % (n, v))
    if head.startswith('nb') and cap in (128, 256):
        lim = {128: (224, 128, 160), 256: (352, 256, 290)}[cap]
        chk(c['Wpeak'] - IDX <= lim[0] * MIB, 'B3f %s: max cdc_raw bytes %.1f MiB <= %d' % (n, c['Wpeak'] / MIB, lim[0]))
        chk(lim[1] * MIB <= c['steadyBytes'] <= lim[2] * MIB + IDX, 'B3f %s: steady state (median last 60 s) %.1f MiB in [%d, %d]' % (n, c['steadyBytes'] / MIB, lim[1], lim[2]))
        chk(c['FreedUp'] > 0 and c['deleteOld'] > 0, 'B3f %s: "Freed up" lines %d, deleteOld passes %d' % (n, c['FreedUp'], c['deleteOld']))
        chk(c['errors'] == 0 and c['WARN'] == 0 and c['forbidden'] == 0, 'B3f %s: client writes succeed throughout (errors %d), no rejection' % (n, c['errors']))
        if cap == 128: chk(4 <= c['steadyLinks'] <= 6, 'B3f %s: steady .log count %s in [4, 6]' % (n, c['steadyLinks']))
        if cap == 256 and g('nb128-r' + n[-1]):
            d = c['steadyBytes'] - g('nb128-r' + n[-1])['steadyBytes']
            chk(abs(d - 128 * MIB) <= S, 'B3f R2-R1 steady difference (rep %s) %.1f MiB = 128 +- 32' % (n[-1], d / MIB))
    if head == 'nb4096':
        chk(c['finalBytes'] >= 1.8 * 1024 * MIB, 'B3f R3: cdc_raw %.0f MiB >= 1.8 GiB' % (c['finalBytes'] / MIB))
        chk(c['FreedUp'] == 0 and c['deleteOld'] == 0 and c['WARN'] == 0, 'B3f R3: no "Freed up" (%d), no deleteOld (%d), no rejection (%d)' % (c['FreedUp'], c['deleteOld'], c['WARN']))
    if head == 'b4096':
        chk(c['errors'] == 0 and c['WARN'] == 0 and c['forbidden'] == 0, 'B3f R5: no rejection (errors %d, WARN %d, forbidden %d)' % (c['errors'], c['WARN'], c['forbidden']))
        chk(c['finalBytes'] >= 1.8 * 1024 * MIB, 'B3f R5: cdc_raw %.0f MiB >= 1.8 GiB' % (c['finalBytes'] / MIB))
    if head in ('b128', 'b256'):
        chk(c['WARN'] > 0 and c['forbidden'] > 0 and c['errors'] > 0, 'B3f %s: rejection evidence: WARN %d, forbidden segments %d, stress errors %d' % (n, c['WARN'], c['forbidden'], c['errors']))
        chk(c['Wpeak'] - IDX <= (cap + 32) * MIB, 'B3f %s: max cdc_raw bytes %.1f MiB <= cap + S = %d' % (n, c['Wpeak'] / MIB, cap + 32))
        chk(c['atWend'] == c['atWend60'], 'B3f %s: stops growing (bytes at W_end-60 s %.1f == at W_end %.1f MiB)' % (n, c['atWend60'] / MIB, c['atWend'] / MIB))
        chk(c['deleteOld'] == 0 and c['FreedUp'] == 0, 'B3f %s: nothing trimmed (deleteOld %d, Freed up %d)' % (n, c['deleteOld'], c['FreedUp']))
        chk(c['release'] is not None and c['release'][0] == 1 and c['release'][1] <= 10000, 'B3f %s: writes resume after two links deleted: %s (accepted, ms; amended criterion 10 s)' % (n, c['release']))
        k = cap // 32
        chk((k - 1) * S <= c['Wpeak'] <= k * S, 'B3f accounting %s: plateau %.1f MiB between (k-1)S and kS = %d..%d' % (n, c['Wpeak'] / MIB, (k - 1) * 32, k * 32))
        if cap == 256 and g('b128-r' + n[-1]):
            d = c['Wpeak'] - g('b128-r' + n[-1])['Wpeak']
            chk(abs(d - 128 * MIB) <= S, 'B3f R6-R4 plateau difference (rep %s) %.1f MiB = 128 +- 32' % (n[-1], d / MIB))
    if head == 'plainnb128':
        chk(c['errors'] == 0 and c['WARN'] == 0, 'B3f plain: no rejection (errors %d, WARN %d)' % (c['errors'], c['WARN']))
        chk(c['Wpeak'] - IDX <= 160 * MIB, 'B3f plain: peak link bytes %.1f MiB <= cap + S = 160' % (c['Wpeak'] / MIB))
        chk(c['finalLinks'] <= 2 and c['finalBytes'] <= 64 * MIB + IDX, 'B3f plain: after final flush %d links, %.1f MiB <= 2 links / 64 MiB' % (c['finalLinks'], c['finalBytes'] / MIB))
        r1 = g('nb128-r1')
        if r1: chk(r1['finalBytes'] >= 96 * MIB, 'B3f plain: R1 at W+30 s keeps %.1f MiB (%d links) >= 96 MiB' % (r1['finalBytes'] / MIB, r1['finalLinks']))
print('\n'.join(out))
print('TOTAL PASS %d MISS %d' % (sum(l.startswith('PASS') for l in out), sum(l.startswith('MISS') for l in out)))
