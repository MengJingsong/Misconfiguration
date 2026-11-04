#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files (step 4 of the protocol); shares no code with the test or cluster-run.py.
usage: selfcheck.py <logs dir of the run: .../run1>   (unit/test.out, cluster/arms.json, cluster/*.csv, cluster/hwb-*.trace, cluster/keys-*.csv)
Unit: re-simulates Session.append from the per-append lines (case 1 logs every append) and counts the check lines.
Cluster: recomputes from the raw files, per arm: values written (keys csv), hint bytes (last hints csv row), slab count and bytes
(trace 'created=' lines), direct pool peak (samples csv), flush-line counters, and compares with arms.json."""
import csv, glob, json, os, re, sys
R = sys.argv[1]
MIB = 1 << 20
bad = 0
def rep(ok, msg):
    global bad
    if not ok: bad += 1
    print(('ok   ' if ok else 'FAIL ') + msg)
# ---- unit
t = os.path.join(R, 'unit/test.out')
if os.path.exists(t):
    L = open(t).read().splitlines()
    chk = [l for l in L if l.startswith('STAGE4 check')]
    rep(all(l.endswith(' ok') for l in chk), f'unit: {len(chk)} check lines, {sum(1 for l in chk if l.endswith("MISMATCH"))} MISMATCH')
    nb = n = 0
    for l in L:
        m = re.match(r'STAGE4 case N=(\d+) h=(\d+) rep=(\d+) entry=(\d+) m=(\d+) total=(\d+) header=(\d+) bytesWritten=(\d+) fileAfterClose=(\d+) channelWrites=(\d+) zeroLengthWriteCalls=(\d+) channelWriteBytes=(\d+) maxWrite=(\d+) maxBufPos=(\d+) directP0=(\d+) directP1=(\d+) directP2=(\d+)', l)
        if not m: continue
        N, h, r, e, cnt, tot, hdr, bw, fa, cw, zc, cwb, mw, mp, p0, p1, p2 = map(int, m.groups())
        n += 1
        pos = 0; w = 0; wb = 0; zc2 = 0
        for _ in range(cnt):
            if e > N - pos:
                if pos: w += 1; wb += pos
                else: zc2 += 1
                pos = 0
            if e <= N - pos: pos += e
            else: w += 1; wb += e
        if pos: w += 1; wb += pos
        ok = (w == cw and wb == cwb == tot == bw and fa == hdr + tot and zc2 == zc and mp <= N and p1 - p0 == N and p2 - p1 <= 0)
        nb += 0 if ok else 1
        if not ok: print('  disagreement', l[:200], w, wb, zc2)
    rep(nb == 0 and n == 36, f'unit: re-simulation of {n} cells (writes, bytes, zero-length calls, pool deltas) from the case lines: {nb} disagreements')
    rep(not any(l.startswith('STAGE4 error') for l in L), 'unit: no STAGE4 error line')
    sm = [l for l in L if l.startswith('STAGE4 summary')]
    print('unit:', sm)
# ---- cluster
C = os.path.join(R, 'cluster')
aj = os.path.join(C, 'arms.json')
if os.path.exists(aj):
    arms = json.load(open(aj))
    for a in arms:
        n = a['name']
        keys = os.path.join(C, f'keys-{n}.csv')
        ok = err = 0
        for l in open(keys):
            p = l.strip().split(',')
            if len(p) == 4:
                if p[3] == 'ok': ok += 1
                else: err += 1
        rep(ok + err == a['written'] and ok == a['succeeded'], f'{n}: keys csv {ok} ok {err} err vs arms.json written {a["written"]} succeeded {a["succeeded"]}')
        hc = os.path.join(C, f'hints-{a["tag"]}.csv')
        rows = [l.split(',') for l in open(hc).read().splitlines()[1:]]
        rows = [list(map(int, r)) for r in rows if len(r) == 5 and r[0].isdigit()]
        win = [r for r in rows if a['t0'] <= r[0] <= a['t1']]
        end = win[-1][1] if win else -1
        rep(abs(end - a['hints_bytes_end']) <= 0.002 * max(1, end) + 1024*1024, f'{n}: hints bytes at the end of the window {end} vs {a["hints_bytes_end"]} (the final listing is a second later)')
        sj = os.path.join(C, f'samples-jmx-{a["tag"]}.csv')
        srows = [l.split(',') for l in open(sj).read().splitlines()[1:]]
        pk = max([float(r[1]) for r in srows if len(r) == 6 and r[0].isdigit() and a['t0'] <= int(r[0]) <= a['t1'] and r[1] not in ('', 'None')] or [0])
        rep(pk == a['direct_peak'], f'{n}: direct peak {pk / MIB:.2f} MiB vs arms.json {a["direct_peak"] / MIB:.2f}')
        tr = os.path.join(C, a['trace_file'])
        cr = []; fl = None; caps = set()
        for l in open(tr, errors='replace'):
            if l.startswith('created='):
                d = dict(x.split('=', 1) for x in l.split() if '=' in x)
                if int(d['ms']) <= a['t1']: cr.append(int(d['size']))
            elif l.startswith('flush'):
                d = dict(x.split('=', 1) for x in l.split()[1:])
                if int(d['ms']) <= a['t1']: fl = d
            elif l.startswith('asamp'):
                d = dict(x.split('=', 1) for x in l.split()[1:])
                if a['t0'] <= int(d['ms']) <= a['t1']: caps.add(int(d['cap']))
        rep(len(cr) == a['slabs_total'] and sum(cr) == a['slab_bytes'], f'{n}: slabs from the trace {len(cr)} x {sorted(set(cr))} vs arms.json {a["slabs_total"]}')
        rep(sorted(caps) == a['trace']['caps'], f'{n}: traced buffer capacities {sorted(caps)}')
        if fl:
            print(f'     {n}: last flush line app={fl["app"]} over={fl["over"]} wrdirect={fl["wrdirect"]} wrzero={fl["wrzero"]} refuse={fl["refuse"]}; Hints_created +{a["hints_created_delta"]}; du {a["du_hints"]}; files {a["hints_files_end"]}')
print('selfcheck: FAIL count', bad)
