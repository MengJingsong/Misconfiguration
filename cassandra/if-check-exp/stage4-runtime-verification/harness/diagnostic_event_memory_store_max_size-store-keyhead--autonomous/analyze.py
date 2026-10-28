#!/usr/bin/env python3
"""Compares the cluster readings (readings.jsonl of every arm) with the B3f predictions as amended 2026-10-27 (C4). usage: analyze.py <logroot>"""
import json, os, sys
root = sys.argv[1]
MiB = 1048576.0
fails = 0
def out(ok, msg):
    global fails
    if not ok: fails += 1
    print(('PASS ' if ok else 'FAIL ') + msg)
arms = {}
for a in ('S-50', 'S-200', 'S-1000', 'L-50', 'L-200', 'L-1000', 'OFF', 'Q-50', 'Q-200', 'Q-1000', 'QOFF'):
    p = os.path.join(root, a, 'readings.jsonl')
    if os.path.exists(p):
        arms[a] = [json.loads(l) for l in open(p)]
for a, rs in arms.items():
    M = rs[0]['M'] if a not in ('OFF', 'QOFF') else 200
    base = next(r for r in rs if r['label'] == '01-baseline-after-schema')
    e0 = base['read_AuditEvent']['count'] if 'read_AuditEvent' in base else 0
    print('== %s (M=%d) baseline events e0=%d bytes[]=%d heap=%d' % (a, M, e0, base['hist_bytes[]'][1], base['heap_used_after_gc']))
    for r in rs:
        if not r['label'].startswith('N'):
            continue
        n = r['N']
        d_b = r['hist_bytes[]'][1] - base['hist_bytes[]'][1]
        d_h = r['heap_used_after_gc'] - base['heap_used_after_gc']
        ae = r['hist_AuditEvent'][0] if r['hist_AuditEvent'] else 0
        cnt = r['read_AuditEvent']['count']
        line = '%s %-16s N=%-6d readEvents=%-5d liveAuditEvent=%-5d dBytes[]=%8.2f MiB dHeap=%8.2f MiB' % (a, r['label'], n, cnt, ae, d_b / MiB, d_h / MiB)
        print(line)
        if a == 'OFF':
            out(abs(d_b) <= 5 * MiB and abs(d_h) <= 5 * MiB and ae == 0, '%s %s: [filed C4, memtable not subtracted] subscription off -> deltas within +-5 MiB and no AuditEvent live (ae=%d)' % (a, r['label'], ae))
            continue
        if a == 'QOFF':
            out(abs(d_b) <= 3 * MiB and ae == 0, '%s %s: [S1] subscription off -> |dBytes[]| %.2f MiB <= 3 MiB, no AuditEvent live (ae=%d)' % (a, r['label'], d_b / MiB, ae))
            continue
        if a.startswith('Q-'):
            expb = ae * 256 * 1024
            out(abs(d_b - expb) <= 0.1 * expb + 1 * MiB, '%s %s: [S1] dBytes[] %.2f MiB within 10%%+1MiB of live AuditEvent %d x 256KiB = %.2f MiB' % (a, r['label'], d_b / MiB, ae, expb / MiB))
            cnt = r['read_AuditEvent']['count']
            out(cnt == min(e0 + n, M), '%s %s: [S1] readEvents count %d == min(e0+N,M)=%d' % (a, r['label'], cnt, min(e0 + n, M)))
            continue
        exp = min(e0 + n, M)
        out(cnt == exp, '%s %s: readEvents count %d == min(e0+N,M)=%d' % (a, r['label'], cnt, exp))
        out(exp <= ae <= exp + 10, '%s %s: live AuditEvent %d in [%d,%d]' % (a, r['label'], ae, exp, exp + 10))
        if a.startswith('L-'):
            expb = exp * 256 * 1024
            if n >= 100:
                out(abs(d_b - expb) <= 0.2 * expb + 2 * MiB, '%s %s: dBytes[] %.2f MiB within 20%%+2MiB of %d x 256KiB = %.2f MiB' % (a, r['label'], d_b / MiB, exp, expb / MiB))
                out(abs(d_h - expb) <= 0.25 * expb + 2 * MiB, '%s %s: dHeap %.2f MiB within 25%%+2MiB of %.2f MiB' % (a, r['label'], d_h / MiB, expb / MiB))
    if a in ('Q-50', 'Q-200'):
        r4 = next(r for r in rs if r['label'] == 'N00400'); r20 = next(r for r in rs if r['label'] == 'N02000')
        b4 = r4['hist_bytes[]'][1] - base['hist_bytes[]'][1]; b20 = r20['hist_bytes[]'][1] - base['hist_bytes[]'][1]
        out(abs(b20 - b4) <= 0.05 * b4, '%s: [S1] dBytes[] at N=2000 (%.2f MiB) within 5%% of N=400 (%.2f MiB)' % (a, b20 / MiB, b4 / MiB))
    if a in ('L-50', 'L-200'):
        r4 = next(r for r in rs if r['label'] == 'N00400'); r20 = next(r for r in rs if r['label'] == 'N02000')
        b4 = r4['hist_bytes[]'][1] - base['hist_bytes[]'][1]; b20 = r20['hist_bytes[]'][1] - base['hist_bytes[]'][1]
        out(abs(b20 - b4) <= 0.1 * b4, '%s: dBytes[] at N=2000 (%.2f MiB) within 10%% of N=400 (%.2f MiB)' % (a, b20 / MiB, b4 / MiB))
# paired difference (main run): L arm minus OFF arm at the same N
if 'OFF' in arms:
    off = {r['label']: r for r in arms['OFF']}
    offb = next(r for r in arms['OFF'] if r['label'] == '01-baseline-after-schema')
    for a in ('L-50', 'L-200', 'L-1000'):
        if a not in arms: continue
        rb = next(r for r in arms[a] if r['label'] == '01-baseline-after-schema')
        for r in arms[a]:
            if r['label'] in off and r['label'].startswith('N'):
                dl = r['hist_bytes[]'][1] - rb['hist_bytes[]'][1]; do = off[r['label']]['hist_bytes[]'][1] - offb['hist_bytes[]'][1]
                dh = (r['heap_used_after_gc'] - rb['heap_used_after_gc']) - (off[r['label']]['heap_used_after_gc'] - offb['heap_used_after_gc'])
                ae = r['hist_AuditEvent'][0]; expb = ae * 256 * 1024
                print('PAIRED %s %s: (ON-OFF) dBytes[]=%.2f MiB dHeap=%.2f MiB; live AuditEvent %d x 256KiB = %.2f MiB; ratio bytes %.4f' % (a, r['label'], (dl - do) / MiB, dh / MiB, ae, expb / MiB, (dl - do) / expb))
                out(abs((dl - do) - expb) <= 0.05 * expb, '%s %s: [paired] ON-OFF dBytes[] within 5%% of live AuditEvent x 256KiB' % (a, r['label']))
if 'S-200' in arms:
    rs = arms['S-200']
    for r in rs:
        if r['label'] in ('N20000-plus30s', 'c5-baseline', 'c5-after250alter', 'drain-after3000'):
            print('S-200', r['label'], {k: v for k, v in r.items() if k.startswith('read_') or k in ('hist_AuditEvent', 'hist_SchemaEvent', 'heap_used_after_gc')})
    c5 = next((r for r in rs if r['label'] == 'c5-after250alter'), None)
    if c5:
        sc = c5['read_SchemaEvent']['count']
        out(sc == 200 or sc <= 200, 'S-200 C5: SchemaEvent count %d <= 200 (200 expected if >=201 were emitted); AuditEvent %d' % (sc, c5['read_AuditEvent']['count']))
        print('INFO second-class: SchemaEvent maxKey (events emitted so far) = %d' % c5['read_SchemaEvent']['maxKey'])
print('FAILS', fails)
