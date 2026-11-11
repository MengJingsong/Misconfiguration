#!/usr/bin/env python3
"""PASS/FAIL per frozen cluster prediction (B3f as amended B5.3). Usage: analyze_cluster.py <run-dir>"""
import json, sys, glob
d = sys.argv[1]
s = json.load(open(d + '/summary.json'))
fail = 0
def check(name, ok, info):
    global fail
    fail += (not ok); print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, info))
EXP = {'102400': 0, '1': 641, '16': 41, '128': 6, 'def': 5, '102401': 5}
TOL = {'1': 3}   # +-1 elsewhere; 640 cuts at 1 MiB allow +-3
peaks = {}
for a in s['arm_results']:
    lab, cap = a['label'], a['cap_mb']
    got = a['log']['Flushed index segment']
    check(lab + ' Flushed-index-segment lines', abs(got - EXP[cap]) <= TOL.get(cap, 1), 'EXPECTED: %d (+-tol)  GOT: %d' % (EXP[cap], got))
    base = a['baseline_histo']['total_bytes']
    pk = 0; inst = 0
    for l in open('%s/histo-%s.jsonl' % (d, lab)):
        h = json.loads(l); pk = max(pk, (h.get('total_bytes') or 0) - base); inst = max(inst, h.get('builder_inst', 0))
    rows = [l.split(',') for l in open(d + '/pool.csv').read().splitlines()[1:] if l.count(',') == 9]
    w = [r for r in rows if a['t_start'] <= int(r[0]) <= a['t_end'] + 8000]
    pend = max([int(r[5]) for r in w] + [0]); oag = max(int(r[4]) for r in w); hu = max(int(r[1]) for r in w)
    peaks[lab] = (cap, pk)
    print('INFO %s cap %s peak live excess over baseline %.1f MB; max OnDiskIndexBuilder instances %d; max SASI-General pending %d; max old-after-GC %.0f MB; max heap used %.0f MB; SI bytes %s; build ms %d' % (lab, cap, pk / 1e6, inst, pend, oag / 1e6, hu / 1e6, [x[1] for x in a['si_after']], a['t_end'] - a['t_start']))
    rev = a['log']['reverting to default']
    check(lab + ' "reverting to default" error line present only for 102401', (rev >= 1) == (cap == '102401'), 'count %d' % rev)
    check(lab + ' no OOM / failure', a['log']['OutOfMemoryError'] == 0 and a['log']['Failed to build index segment'] == 0 and a['log']['Failed to flush index'] == 0, a['log'])
by = {}
for lab, (cap, pk) in peaks.items(): by.setdefault(cap, []).append(pk)
m = {c: max(v) for c, v in by.items()}
check('peak live excess ordered 1 < 16 < 128 < default < 102400', m['1'] < m['16'] < m['128'] < m['def'] < m['102400'], {k: round(v / 1e6, 1) for k, v in m.items()})
check('ratio peak(102400)/peak(1) > 5', m['102400'] / max(1, m['1']) > 5, 'ratio %.1f' % (m['102400'] / max(1, m['1'])))
p = {lab: pk for lab, (cap, pk) in peaks.items()}
r1 = p['a6-102401'] / m['def']; check('peak(102401) within 25% of peak(default)', abs(r1 - 1) <= 0.25, 'ratio %.2f' % r1)
r2 = m['102400'] / p['a6-102401']; check('peak(102400) >= 1.10 x peak(102401)', r2 >= 1.10, 'ratio %.2f' % r2)
a, b = p['a1-102400'], p['a7-102400']; check('the two 102400 arms agree within 10%', abs(a - b) / max(a, b) <= 0.10, '%.0f vs %.0f MB' % (a / 1e6, b / 1e6))
print('FAILS', fail); sys.exit(1 if fail else 0)
