#!/usr/bin/env python3
"""PASS/FAIL per frozen cluster prediction (B3f as amended B5.3). Usage: analyze_cluster.py <run-dir>"""
import json, sys, glob
d = sys.argv[1]
s = json.load(open(d + '/summary.json'))
fail = 0
def check(name, ok, info):
    global fail
    fail += (not ok); print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, info))
EXP = {'1024': 0, '8': 81, '32': 21, '128': 6, 'def': 5}
peaks = {}
for a in s['arm_results']:
    lab, cap = a['label'], a['cap_mb']
    got = a['log']['Flushed index segment']
    check(lab + ' Flushed-index-segment lines', abs(got - EXP[cap]) <= 1, 'EXPECTED: %d (+-1)  GOT: %d' % (EXP[cap], got))
    base = a['baseline_histo']['total_bytes']
    pk = 0; inst = 0
    for l in open('%s/histo-%s.jsonl' % (d, lab)):
        h = json.loads(l); pk = max(pk, (h.get('total_bytes') or 0) - base); inst = max(inst, h.get('builder_inst', 0))
    rows = [l.split(',') for l in open(d + '/pool.csv').read().splitlines()[1:] if l.count(',') == 9]
    w = [r for r in rows if a['t_start'] <= int(r[0]) <= a['t_end'] + 8000]
    pend = max([int(r[5]) for r in w] + [0]); oag = max(int(r[4]) for r in w); hu = max(int(r[1]) for r in w)
    peaks[lab] = (cap, pk)
    print('INFO %s cap %s peak live excess over baseline %.1f MB; max OnDiskIndexBuilder instances %d; max SASI-General pending %d; max old-after-GC %.0f MB; max heap used %.0f MB; SI bytes %s; build ms %d' % (lab, cap, pk / 1e6, inst, pend, oag / 1e6, hu / 1e6, [x[1] for x in a['si_after']], a['t_end'] - a['t_start']))
    check(lab + ' no OOM / failure', a['log']['OutOfMemoryError'] == 0 and a['log']['Failed to build index segment'] == 0 and a['log']['Failed to flush index'] == 0, a['log'])
by = {}
for lab, (cap, pk) in peaks.items(): by.setdefault(cap, []).append(pk)
m = {c: max(v) for c, v in by.items()}
check('peak live excess ordered 8 < 32 < 128 < default < 1024', m['8'] < m['32'] < m['128'] < m['def'] < m['1024'], {k: round(v / 1e6, 1) for k, v in m.items()})
check('ratio peak(1024)/peak(8) > 5', m['1024'] / max(1, m['8']) > 5, 'ratio %.1f' % (m['1024'] / max(1, m['8'])))
print('FAILS', fail); sys.exit(1 if fail else 0)
