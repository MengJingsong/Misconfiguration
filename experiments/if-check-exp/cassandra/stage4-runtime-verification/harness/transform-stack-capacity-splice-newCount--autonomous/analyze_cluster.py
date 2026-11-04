#!/usr/bin/env python3 -I
"""PASS/FAIL of the frozen cluster predictions C1-C5 (case file B3i.5). Usage: analyze_cluster.py <outdir>"""
import sys, os, json, csv
out = sys.argv[1]
R = json.load(open(os.path.join(out, 'phases.json')))
res = []
def chk(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ('  ' + detail if detail else ''))
def samples(name):
    rows = list(csv.DictReader(open(os.path.join(out, name))))
    return rows
ARR = ['[Lorg.apache.cassandra.db.transform.Transformation;_bytes', '[Lorg.apache.cassandra.db.transform.Stack$MoreContentsHolder;_bytes', 'org.apache.cassandra.db.transform.Stack$MoreContentsHolder_bytes']
def arrbytes(r): return sum(int(r[c]) for c in ARR)
Ls = sorted(R['scan'], key=lambda k: R['scan'][k]['L'])
Gtot = 0; maxnew = 0
for k in Ls:
    v = R['scan'][k]
    dS = sum(v['trace_after'][n]['S'] - v['trace_before'][n]['S'] for n in '12'); dG = sum(v['trace_after'][n]['G'] - v['trace_before'][n]['G'] for n in '12')
    dSRP = sum(v['trace_after'][n]['SRP'] - v['trace_before'][n]['SRP'] for n in '12'); dlog = sum(v['srp_log_after'][n] - v['srp_log_before'][n] for n in '12')
    Gtot += dG; maxnew = max(maxnew, *(v['trace_after'][n]['max_newCount'] for n in '12'))
    chk('C1 %s: splice entries S>=1' % k, dS >= 1, 'S=%d' % dS)
    if v['L'] >= 2000: chk('C1 %s: short-read rule hits >=1' % k, dSRP >= 1 and dlog >= 1, 'SRP rule=%d, log lines "for short read protection"=%d' % (dSRP, dlog))
    else: print('INFO %s: SRP rule=%d log=%d (no prediction for L<2000)' % (k, dSRP, dlog))
    print('INFO %s: scans=%d rows_per_scan=%s mean_secs=%s G=%d' % (k, v['nscans'], v['rows_per_scan'], v['mean_secs'], dG))
chk('C2 grow branch (line 95) count G == 0 over all scans', Gtot == 0, 'G=%d; largest newCount seen on either node=%d' % (Gtot, maxnew))
maxarr = {}; maxtot = {}; maxfrac = 0
for k in Ls:
    rows = samples('samples-%s.csv' % k)
    ab = [arrbytes(r) for r in rows]; fr = max(arrbytes(r) / int(r['total_bytes']) for r in rows)
    maxfrac = max(maxfrac, fr)
    maxarr[k] = max(ab); maxtot[k] = max(int(r['total_bytes']) for r in rows if r['node'] == '1')
    chk('C3 %s: array bytes < 1 MiB in all %d samples and < 0.5%% of total' % (k, len(rows)), max(ab) < 2**20 and fr < 0.005, 'max array bytes=%d max fraction=%.5f' % (max(ab), fr))
lo, hi = Ls[0], Ls[-1]
chk('C4 heap follows L: max live total (node 1) %s - %s >= 20 MiB' % (hi, lo), maxtot[hi] - maxtot[lo] >= 20 * 2**20, '%s=%d %s=%d diff=%.1f MiB' % (hi, maxtot[hi], lo, maxtot[lo], (maxtot[hi] - maxtot[lo]) / 2**20))
chk('C4 arrays do not grow with L: max array bytes %s < 4 x %s + 64 KiB' % (hi, lo), maxarr[hi] < 4 * maxarr[lo] + 65536, '%s=%d %s=%d' % (hi, maxarr[hi], lo, maxarr[lo]))
kk = 'org.apache.cassandra.cache.KeyCacheKey_bytes'
off = max(int(r[kk]) for r in samples('samples-keycache_off.csv')); on = max(int(r[kk]) for r in samples('samples-keycache_64.csv'))
chk('C5 control: KeyCacheKey live bytes off < 0.5 MiB, on - off >= 2 MiB', off < 0.5 * 2**20 and on - off >= 2 * 2**20, 'off=%d on=%d; %s | %s' % (off, on, R['control']['keycache_off']['key_cache_line'], R['control']['keycache_64']['key_cache_line']))
print('SUMMARY %d PASS, %d FAIL' % (sum(res), len(res) - sum(res)))
