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
    cells = {}
    for l in L:
        m = re.match(r'STAGE4 append (heapagg )?N=(\d+) H=(\d+) rep=(\d+) i=(\d+) bytesWritten=(\d+) fileLen=(\d+) bufPos=(\d+)', l)
        if m:
            cells.setdefault((m.group(1) or '', int(m.group(2)), int(m.group(3)), int(m.group(4))), []).append(tuple(int(x) for x in m.groups()[4:]))
    hdr = None
    for l in L:
        m = re.match(r'STAGE4 case (heapagg )?N=(\d+) H=(\d+) rep=(\d+) entry=(\d+) k=(\d+) header=(\d+)', l)
        if m:
            hdr = int(m.group(7)); break
    nb = 0
    for (hp, n, h, rep_), rows in sorted(cells.items()):
        e = h + 12; pos = 0; f = hdr; ok = True
        for i, bw, fl, bp in rows:
            if e > n - pos:
                f += pos; pos = 0
            if e <= n - pos: pos += e
            else: f += e
            ok &= (bp == pos and fl == f and bw == (i + 1) * e)
        nb += 0 if ok else 1
        mx = max(r[3] for r in rows)
        ok2 = mx <= n
        nb += 0 if ok2 else 1
    rep(nb == 0, f'unit: re-simulation of {len(cells)} cells from the per-append lines: {nb} disagreements (header {hdr} B)')
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
