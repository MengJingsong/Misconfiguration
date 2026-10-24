#!/usr/bin/env python3
"""Readings and EXPECTED checks for the cluster tier of commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous (B3f / B3g / B2i.7).
Usage: python3 -I analyze_cluster.py <outroot>   (arm dirs written by cluster-run.sh: ds.csv, ds.perfile.csv, jmx.csv, times.txt)"""
import sys, os, csv, glob, math
root = sys.argv[1]
MiB = 1 << 20
res = {}
for d in sorted(glob.glob(os.path.join(root, '*/'))):
    arm = os.path.basename(d.rstrip('/'))
    if not os.path.exists(d + 'DONE'):
        print(f'ARM {arm}: not DONE'); continue
    t = dict(kv.split('=') for kv in open(d + 'times.txt').read().split())
    S = int(t['S']) * MiB; mode = t['MODE']; tot = int(t['TOTAL']); load = t['LOAD']; n = int(t['N'])
    T0, T1, TS = int(t['T0']), int(t['T1']), int(t['TS'])
    ds = list(csv.DictReader(open(d + 'ds.csv')))
    pf = list(csv.DictReader(open(d + 'ds.perfile.csv')))
    run = [r for r in ds if T0 <= int(r['t_ms']) <= TS]
    peak_files = max(int(r['nfiles']) for r in run); peak_total = max(int(r['totalbytes']) for r in run)
    maxfile = max(int(r['maxfile']) for r in ds)
    maps_peak = max(int(r['maps_bytes']) for r in ds); maps_n = max(int(r['maps_n']) for r in ds)
    per_max = max(int(r['max_size']) for r in pf)
    created = [r for r in pf if int(r['first_ms']) >= T0 - 1000]
    jmx = []
    for ln in open(d + 'jmx.csv'):
        p = ln.strip().split(',')
        if len(p) == 2 and p[1].lstrip('-').isdigit() and T0 <= int(p[0]) <= TS: jmx.append(int(p[1]))
    jpeak = max(jmx) if jmx else -1
    base_files = [r for r in pf if int(r['first_ms']) < T0 - 1000]
    flush = '; '.join(l.strip() for l in open(d + 'counts.txt') if ' system' not in l)
    # expectations
    est_rolls = 30 if load != 'none' else 0   # B3g: fewer than about 30 segment rolls = limit not reached
    ok = {}
    ok['no file > S (mmap) / within bound (lz4)'] = (per_max <= S) if mode == 'mmap' else None
    if mode == 'lz4':
        life = {r['name']: 1 for r in pf}
        bound = S + math.ceil(S / 255) + 32 * (int(((TS - T0) / 1000.0) * 10) + 8) + 64   # at most one sync per 100 ms (generous: whole run)
        ok['no file > S (mmap) / within bound (lz4)'] = per_max <= bound
    if mode == 'mmap' and load != 'none':
        ok['largest observed == S'] = per_max == S
    soft = f"peak live files {peak_files} vs soft prediction {tot // (S // MiB) + 1}-{tot // (S // MiB) + 2} (+ overshoot allowed)"
    if load in ('stress', 'loader'):
        ok['rolls >= est'] = len(created) >= est_rolls
    res[arm] = dict(S=S, mode=mode, tot=tot, per_max=per_max, peak_total=peak_total, peak_files=peak_files, created=len(created), jpeak=jpeak, ok=ok)
    print(f"ARM {arm}: S={S//MiB}MiB mode={mode} total_space={tot}MiB load={load} n={n} load_s={(T1-T0)//1000}")
    print(f"   largest file (stat, all samples)={maxfile} ({maxfile/MiB:.3f} MiB; S={S//MiB}) | per-file max over names={per_max} | files seen during run (created)={len(created)} (est>= {est_rolls:.0f}) | idle baseline files={len(base_files)}")
    print(f"   peak live files={peak_files} peak total(stat)={peak_total/MiB:.1f} MiB peak JMX TotalCommitLogSize={jpeak/MiB:.1f} MiB | maps peak n={maps_n} bytes={maps_peak/MiB:.1f} MiB | flush reasons: {flush}")
    print(f"   SOFT: {soft}")
    print(f"   EXPECTED: " + ' | '.join(f'{k}: {v}' for k, v in ok.items() if v is not None))
# scaling and control
mm = {a: r for a, r in res.items() if r['mode'] == 'mmap' and r['tot'] == 1024}
if len(mm) >= 3:
    s = sorted(mm.values(), key=lambda r: r['S'])
    print('SCALING largest-file ratios (S=%s): %s' % (','.join(str(r['S']//MiB) for r in s), [r['per_max'] / s[0]['per_max'] for r in s]))
ctl = [r for r in res.values() if r['tot'] != 1024]
for c in ctl:
    base = [r for r in res.values() if r['S'] == c['S'] and r['tot'] == 1024 and r['mode'] == c['mode']]
    if base:
        print(f"CONTROL total_space={c['tot']}MiB S={c['S']//MiB}: peak files {c['peak_files']} (expected about 8-10) peak dir {c['peak_total']/MiB:.1f} MiB vs 1024 MiB-run peak files {base[0]['peak_files']} dir {base[0]['peak_total']/MiB:.1f} MiB")
