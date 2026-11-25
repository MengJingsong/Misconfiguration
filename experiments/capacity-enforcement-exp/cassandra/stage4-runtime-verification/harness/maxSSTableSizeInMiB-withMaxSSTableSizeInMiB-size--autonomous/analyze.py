#!/usr/bin/env python3
"""o114 analysis: parse the driver logs and per-run logs of run1/, check B2f/B3f with the S4-A2/S4-A3 thresholds.
usage: analyze.py <run1 dir>   (expects <dir>/logs/*.log copied from the node)"""
import re, sys, os, math, glob

D = sys.argv[1]
L_ = os.path.join(D, 'logs')
MiB = 1 << 20


def parse_driver(path):
    runs = {}
    cur = None
    for line in open(path, errors='replace'):
        m = re.match(r'^\+ \S+/run\.sh (\S+) (.*)$', line)
        if m:
            cur = m.group(1); runs[cur] = {'args': m.group(2)}; continue
        if cur is None:
            continue
        r = runs[cur]
        line = line.rstrip('\n')
        if line.startswith('exit='): r['exit'] = int(line[5:])
        elif line.startswith('WRITER'): r['limit_bytes'] = int(line.split()[-1])
        elif line.startswith('SUMMARY'):
            for kv in line.split()[1:]:
                k, v = kv.split('=', 1)
                try: r[k] = int(v)
                except ValueError: r[k] = v
        elif line.startswith('data_files='): r['data_files'] = int(line.split('=')[1])
        elif line.startswith('data_sizes='): r['data_sizes'] = [int(x) for x in line.split('=')[1].split()]
        elif line.startswith('data_by_id='):
            r['by_id'] = [int(x.split(':')[1]) for x in line.split('=')[1].split()]
        elif line.startswith('du_bytes='):
            v = line.split('=')[1]; r['du'] = int(v) if v else None
        elif 'OutOfMemoryError' in line: r['oom'] = True
    return runs


def heap(tag):
    p = os.path.join(L_, tag + '.log')
    if not os.path.exists(p): return []
    return [(int(m.group(1)), int(m.group(2))) for m in
            re.finditer(r'HEAP_SAMPLE row=(\d+) live_bytes=(\d+)', open(p, errors='replace').read())]


def ok(b): return 'PASS' if b else 'FAIL'


out = []
pr = out.append

unit = {}
if os.path.exists(os.path.join(L_, 'driver-unit.log')):
    unit = parse_driver(os.path.join(L_, 'driver-unit.log'))
    pr('=== UNIT TIER (B2f) ===')
    s = None
    for t in ('u-ins-1', 'u-ins-4', 'u-ins-16'):
        r = unit[t]; L = int(t.split('-')[-1]); Lb = L * MiB; s = r['first_row_delta']
        N = r['rows']; n = math.ceil(N * s / Lb)
        nonlast = r['by_id'][:-1]
        band = all(0.85 * Lb <= x <= 1.15 * Lb for x in nonlast)
        c1 = r['limit_bytes'] == Lb
        c2 = Lb - s < r['max_operand'] <= Lb
        c3 = abs(r['syncs'] - (n - 1)) <= 1
        c4 = abs(r['data_files'] - n) <= 1
        pr(f"{t}: exit={r['exit']} limit={r['limit_bytes']} s={s} n(L)={n} max_operand={r['max_operand']} syncs={r['syncs']} files={r['data_files']} "
           f"nonlast[min,max]=[{min(nonlast) if nonlast else '-'},{max(nonlast) if nonlast else '-'}] du={r['du']}")
        pr(f"   limit {ok(c1)}  operand in (L-s,L] {ok(c2)}  syncs n-1+-1 {ok(c3)}  files n+-1 {ok(c4)}  nonlast in [0.85,1.15]L {ok(band)}")
    f1, f16 = unit['u-ins-1']['data_files'], unit['u-ins-16']['data_files']
    pr(f"file-count scaling: files(1)/files(16) = {f1}/{f16} = {f1/f16:.2f}  (row-3 threshold: < 4 => refuted) {ok(f1 >= 4*f16)}")
    for t in ('u-def-unset', 'u-def-0', 'u-def--1'):
        r = unit[t]
        pr(f"{t}: exit={r['exit']} limit={r['limit_bytes']} max_operand={r['max_operand']} syncs={r['syncs']} files={r['data_files']} by_id={r['by_id']}"
           f"  [pred limit 134217728 {ok(r['limit_bytes']==134217728)}; syncs=1 {ok(r['syncs']==1)}; files=2 {ok(r['data_files']==2)}; "
           f"first in [109,147] MiB {ok(109*MiB <= r['by_id'][0] <= 147*MiB)}; operand in (128MiB-s,128MiB] {ok(134217728 - r['first_row_delta'] < r['max_operand'] <= 134217728)}]")
    for t in ('s-def-unset', 's-def-0', 's-def--1'):
        r = unit[t]
        pr(f"{t}: exit={r['exit']} limit={r['limit_bytes']} max_operand={r['max_operand']} switches={r['switches']} files={r['data_files']} by_id={r['by_id']}"
           f"  [pred limit -1048576 {ok(r['limit_bytes']==-1048576)}; switches=0 {ok(r['switches']==0)}; files=1 {ok(r['data_files']==1)}]")
    for t in ('s-ins-1', 's-ins-4', 's-ins-16'):
        r = unit[t]; L = int(t.split('-')[-1]); Lb = L * MiB
        sdisk = sum(r['by_id']) / r['rows']
        n = math.ceil(r['rows'] * sdisk / Lb)
        nonlast = r['by_id'][:-1]
        band = all(Lb < x <= Lb + 2048 for x in nonlast)
        pr(f"{t}: exit={r['exit']} limit={r['limit_bytes']} s_disk={sdisk:.1f} n={n} max_operand={r['max_operand']} switches={r['switches']} "
           f"min_at_switch={r['min_at_switch']} max_at_switch={r['max_at_switch']} files={r['data_files']} nonlast[min,max]=[{min(nonlast)},{max(nonlast)}] du={r['du']}")
        pr(f"   limit {ok(r['limit_bytes']==Lb)}  switches=files-1 {ok(r['switches']==r['data_files']-1)}  files n+-1 {ok(abs(r['data_files']-n)<=1)}  "
           f"nonlast in (L,L+2048] {ok(band)}  min_at_switch>L {ok(r['min_at_switch']>Lb)}  max_operand<=L+2048 {ok(r['max_operand']<=Lb+2048)}")
    r = unit['u-del-1']
    pr(f"u-del-1: exit={r['exit']} limit={r['limit_bytes']} first_row_delta={r['first_row_delta']} max_operand={r['max_operand']} syncs={r['syncs']} files={r['data_files']} by_id={r['by_id']}"
       f"  [pred operand>=4194304 {ok(r['max_operand']>=4194304)}; syncs=0 {ok(r['syncs']==0)}; files=1 {ok(r['data_files']==1)}]")

if os.path.exists(os.path.join(L_, 'driver-cluster.log')):
    cl = parse_driver(os.path.join(L_, 'driver-cluster.log'))
    pr('')
    pr('=== CLIENT-PROCESS TIER (B3f) ===')
    H0 = cl['p-u-16']['min_live_heap']
    pr(f"H0 = min_live_heap(p-u-16) = {H0} B = {H0/MiB:.1f} MiB")
    P = {}
    for t, L in (('p-u-16', 16), ('p-u-64', 64), ('p-u-unset', 128), ('p-u-256', 256), ('p-u-1024', 1024)):
        r = cl[t]; P[L] = (r['max_live_heap'] - H0) / MiB
        hs = heap(t)
        T = r['rows'] * r['first_row_delta']
        n = math.ceil(T / (L * MiB))
        nonlast = r['by_id'][:-1]
        band = all(0.85 * L * MiB <= x <= 1.15 * L * MiB for x in nonlast) if nonlast else True
        pr(f"{t}: exit={r['exit']} limit={r['limit_bytes']} s={r['first_row_delta']} T={T/MiB:.1f}MiB syncs={r['syncs']} max_operand={r['max_operand']} "
           f"min_live={r['min_live_heap']/MiB:.1f}MiB max_live={r['max_live_heap']/MiB:.1f}MiB P={P[L]:.1f}MiB P/L={P[L]/L:.2f} "
           f"files={r['data_files']} (pred {n}+-1 {ok(abs(r['data_files']-n)<=1)}) nonlast band {ok(band)} du={r['du']} samples={len(hs)} elapsed={r['elapsed_s']}s")
        if hs:
            pr("   samples MiB (every 8th): " + ' '.join(f"{(b-H0)/MiB:.0f}" for _, b in hs[::8]) + f" | last {(hs[-1][1]-H0)/MiB:.0f}")
    Ps = [P[16], P[64], P[128], P[256]]
    pr(f"P(16,64,128,256) = {', '.join(f'{x:.1f}' for x in Ps)} MiB")
    pr(f"  strictly increasing {ok(all(b > a for a, b in zip(Ps, Ps[1:])))}")
    pr(f"  P/L in [0.6,4.0] for L>=64: {[round(P[L]/L,2) for L in (64,128,256)]} {ok(all(0.6 <= P[L]/L <= 4.0 for L in (64,128,256)))}")
    pr(f"  P(256)-P(64) = {P[256]-P[64]:.1f} >= 150 {ok(P[256]-P[64] >= 150)}")
    pr(f"  P(16) = {P[16]:.1f} <= 80 {ok(P[16] <= 80)}")
    pr(f"  flat? max-min = {max(Ps)-min(Ps):.1f} (<= 32 => flat)")
    rc = cl['p-u-1024']; T = rc['rows'] * rc['first_row_delta']; hs = heap('p-u-1024')
    last = (hs[-1][1] - H0) / MiB if hs else float('nan')
    pr(f"  control L=1024: last sample {last:.1f} MiB above H0 >= 0.8T={0.8*T/MiB:.1f} {ok(last >= 0.8*T/MiB)}; syncs={rc['syncs']} (=0 {ok(rc['syncs']==0)}); files={rc['data_files']} (=1 {ok(rc['data_files']==1)})")
    Ps16 = (cl['p-s-16']['max_live_heap'] - H0) / MiB; Ps256 = (cl['p-s-256']['max_live_heap'] - H0) / MiB
    pr(f"  sorted: P_s(16)={Ps16:.1f} P_s(256)={Ps256:.1f} |diff|={abs(Ps256-Ps16):.1f} <= 32 {ok(abs(Ps256-Ps16) <= 32)}; both <= P(16)+32={P[16]+32:.1f} {ok(max(Ps16,Ps256) <= P[16]+32)}")
    for t, L in (('p-s-16', 16), ('p-s-256', 256)):
        r = cl[t]; nonlast = r['by_id'][:-1]; Lb = L * MiB
        pr(f"  {t}: exit={r['exit']} files={r['data_files']} switches={r['switches']} nonlast in (L,L+2048] {ok(all(Lb < x <= Lb+2048 for x in nonlast))} "
           f"[{min(nonlast)},{max(nonlast)}] du={r['du']}")
    dus = [cl[t]['du'] for t in ('p-u-16', 'p-u-64', 'p-u-unset', 'p-u-256', 'p-u-1024', 'p-s-16', 'p-s-256')]
    pr(f"  du_bytes: {dus}  spread {(max(dus)-min(dus))/min(dus)*100:.2f}% (<=3% {ok((max(dus)-min(dus))/min(dus) <= 0.03)})")
    for t in ('p-oom-16', 'p-oom-256'):
        r = cl.get(t, {})
        pr(f"  {t}: exit={r.get('exit')} oom={r.get('oom', False)} files={r.get('data_files')} summary={'yes' if 'max_operand' in r else 'no'}")

print('\n'.join(out))
