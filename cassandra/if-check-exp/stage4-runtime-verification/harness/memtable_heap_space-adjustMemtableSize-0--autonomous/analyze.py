#!/usr/bin/env python3
"""Readings and decision tables (case file A-U2 for B2g, A-K5 for B3g) of
memtable_heap_space-adjustMemtableSize-0--autonomous.

Usage: python3 -I analyze.py unit <unit.csv>
       python3 -I analyze.py cluster <log root ~/stage4-logs/sai> <unit.csv>
Prints readings, every sub-prediction as HIT/MISS, and the first matching row.
"""
import glob, os, re, statistics, sys

MiB = 1 << 20
PK = 'org.apache.cassandra.index.sai.utils.PrimaryKey$Factory$SkinnyPrimaryKey'
CLASSES = {PK: 'SkinnyPK', 'org.apache.cassandra.index.sai.utils.PrimaryKeys': 'PrimaryKeys',
           'org.apache.cassandra.db.BufferDecoratedKey': 'BufDecKey',
           'org.apache.cassandra.dht.Murmur3Partitioner$LongToken': 'LongToken'}


def hm(ok):
    return 'HIT ' if ok else 'MISS'


# ---------------------------------------------------------------- unit
def unit(path, quiet=False):
    rows = [l.strip().split(',') for l in open(path) if l.strip()]
    u1 = [r for r in rows if r[0] == 'U1U2' and r[1] != 'N']
    u3 = [r for r in rows if r[0] == 'U3' and r[1] != 'withIndex']
    out = {}
    p = (lambda *a: None) if quiet else print
    if len(u1) != 1:
        p('U1 rows:', len(u1)); return None
    N, W, S, dS, dP, diff, D, D2, K, fl = map(int, u1[0][1:])
    r_unit = (D - K) / S if S else float('nan')
    out.update(N=N, W=W, S=S, dS=dS, dP=dP, diff=diff, D=D, D2=D2, K=K, fl=fl, r_unit=r_unit)
    p(f'U1: N={N} W={W} S={S} dS={dS} dP={dP} dS-dP={diff} (dS-dP-S={diff - S}) flushes={fl}')
    p(f'U2: D={D} D2={D2} K={K} (D-K)/S={r_unit:.3f} (D-K)-S={D - K - S} = {(D - K - S) / N:.1f} B/row')
    sub = [('U1 dS-dP == S exactly', diff == S), ('U1 S > 0', S > 0), ('U1 W == N', W == N), ('U1 flushes == 0', fl == 0),
           ('U1 S/N in 100..400 (%.1f)' % (S / N), 100 <= S / N <= 400),
           ('U2 r_unit in 1.2..2.5 (%.3f)' % r_unit, 1.2 <= r_unit <= 2.5),
           ('U2 (D-K)-S >= 100*N', D - K - S >= 100 * N), ('U2 D2 <= D', D2 <= D)]
    per = {}
    for r in u3:
        wi, L, n, P, owns, s, f = r[1] == 'true', int(r[2]), int(r[3]), int(r[4]), int(r[5]), int(r[6]), int(r[7])
        per.setdefault((L, wi), []).append((n, P, owns, s, f))
    U3 = {}
    for (L, wi), v in sorted(per.items()):
        v.sort()
        flushes = v[-1][4] - v[0][4]
        maxP = max(x[1] for x in v); maxS = max(x[3] for x in v)
        decs = sum(1 for a, b in zip(v, v[1:]) if b[3] < a[3])
        U3[(L, wi)] = dict(flushes=flushes, maxP=maxP, maxS=maxS, decs=decs, n=len(v), rows=v[-1][0])
        p(f'U3 L={L // MiB}MiB index={wi}: samples={len(v)} rows={v[-1][0]} flushes={flushes} maxPool={maxP} ({maxP / L:.3f} L) '
          f'maxS={maxS} ({maxS / L:.3f} L) S decreases={decs}')
    out['U3'] = U3
    Ls = sorted({k[0] for k in U3})
    ok3 = len(Ls) == 2 and all((L, w) in U3 for L in Ls for w in (True, False))
    if ok3:
        L32, L96 = Ls
        fs = {L: U3[(L, True)]['flushes'] for L in Ls}; fp = {L: U3[(L, False)]['flushes'] for L in Ls}
        ms = {L: U3[(L, True)]['maxS'] for L in Ls}
        pred = dS / dP if dP else float('nan')
        for L in Ls:
            rr = fs[L] / fp[L] if fp[L] else float('inf')
            sub.append((f'U3 L={L // MiB} flushes(sai)/flushes(plain)={rr:.3f} within 25% of dS/dP={pred:.3f}', abs(rr / pred - 1) <= 0.25))
            sub.append((f'U3 L={L // MiB} every poolUsed <= L', max(U3[(L, True)]['maxP'], U3[(L, False)]['maxP']) <= L))
            sub.append((f'U3 L={L // MiB} every S <= L', ms[L] <= L))
            sub.append((f'U3 L={L // MiB} peak S <= L/2', ms[L] <= L / 2))
        fr = fs[L32] / fs[L96] if fs[L96] else float('inf'); mr = ms[L96] / ms[L32] if ms[L32] else float('inf')
        sub.append((f'U3 flushes(32)/flushes(96) = {fr:.3f} in 3 +- 1', 2 <= fr <= 4))
        sub.append((f'U3 maxS(96)/maxS(32) = {mr:.3f} in 2..4', 2 <= mr <= 4))
        out.update(fr=fr, mr=mr)
    p('\nUnit sub-predictions (B2f):')
    for name, ok in sub:
        p(f'  {hm(ok)} {name}')
    # ---- A-U2 decision
    row = None
    if not ok3:
        row = (1, 'Invalid (U3 incomplete)')
    else:
        allP = max(U3[(L, w)]['maxP'] for L in Ls for w in (True, False))
        if fl != 0 or U3[(L32, False)]['flushes'] == 0:
            row = (1, 'Invalid')
        elif (diff == 0 and S > 0) or any(fs[L] <= fp[L] for L in Ls):
            row = (2, 'Refuted - charge not applied / not governing')
        elif abs(diff - S) > 0.01 * S:
            row = (3, 'Refuted - mis-charge factor %.3f' % (diff / S))
        elif any(ms[L] > L for L in Ls) or any(U3[(L, w)]['maxP'] > 1.25 * L for L in Ls for w in (True, False)):
            row = (4, 'Refuted - usage exceeds the limit')
        elif any(U3[(L, True)]['flushes'] >= 3 and U3[(L, True)]['decs'] == 0 for L in Ls):
            row = (5, 'Refuted - index not released')
        elif fr < 1.5 and mr < 1.5:
            row = (6, 'Refuted - flat across the knob')
        elif (abs(diff - S) <= 0.01 * S and all(fs[L] > fp[L] for L in Ls)
              and all(U3[(L, True)]['decs'] >= 3 and ms[L] <= L / 2 for L in Ls) and fr >= 1.5 and mr >= 1.5):
            row = (7, 'Confirmed - caps')
        else:
            row = (8, 'Not confirmed (no matching row)')
        q = []
        if any(L < U3[(L, w)]['maxP'] <= 1.25 * L for L in Ls for w in (True, False)):
            q.append('Qa poolUsed above L by up to 25%')
        if r_unit > 3: q.append('Qb (D-K)/S > 3')
        if r_unit <= 1: q.append('Qc (D-K)/S <= 1')
        p(f'\nUNIT ROW: {row[0]} {row[1]}; qualifiers: {q or "none"}')
    out['row'] = row
    return out


# ---------------------------------------------------------------- cluster
def hist(path):
    tot = None; cls = {}
    for line in open(path, errors='replace'):
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', line)
        if m and m.group(3) in CLASSES:
            cls[CLASSES[m.group(3)]] = (int(m.group(1)), int(m.group(2)))
        m = re.match(r'Total\s+(\d+)\s+(\d+)', line)
        if m:
            tot = int(m.group(2))
    return tot, cls


def run(d, L):
    r = {'L': L}
    rl = open(os.path.join(d, 'run.log'), errors='replace').read()
    r['died'] = 'NODE DIED' in rl
    m = re.search(r'OOM/crash evidence: (.*)', rl); r['oom'] = m.group(1).strip() if m else '?'
    r['threshold'] = re.search(r'Global memtable on-heap threshold is enabled at (\d+)MiB', rl)
    r['threshold'] = int(r['threshold'].group(1)) if r['threshold'] else None
    cons = open(os.path.join(d, 'stress-console.log'), errors='replace').read() if os.path.exists(os.path.join(d, 'stress-console.log')) else ''
    m = re.search(r'Total partitions\s*:\s*([\d,]+)', cons); r['partitions'] = int(m.group(1).replace(',', '')) if m else 0
    m = re.search(r'Total errors\s*:\s*([\d,]+)', cons); r['errors'] = int(m.group(1).replace(',', '')) if m else -1
    m = re.search(r'Op rate\s*:\s*([\d,]+)', cons); r['oprate'] = m.group(1) if m else '?'
    t0 = int(open(os.path.join(d, 't-start-stress')).read()); t1 = int(open(os.path.join(d, 't-end-stress')).read())
    r['dur'] = (t1 - t0) / 1000
    fl = [l for l in open(os.path.join(d, 'flushes.txt'))]
    r['flushes'] = sum('Reason: MEMTABLE_LIMIT' in l for l in fl); r['other'] = len(fl) - r['flushes']
    used = [float(m.group(1)) for l in open(os.path.join(d, 'trig.txt')) for m in [re.search(r'Used total: ([\d.]+)/', l)] if m]
    r['usedmax'] = max(used) if used else None; r['ntrig'] = len(used)
    this = [l for l in open(os.path.join(d, 'trig.txt'))]
    r['trig_other_table'] = sum(1 for l in this if "Keyspace='saiks'" not in l)  # display fix after run 1 (format CFS(Keyspace=...))
    rows = []
    for l in open(os.path.join(d, 'samples.csv')):
        if l.startswith('epoch'): continue
        v = l.strip().split(',')
        if len(v) == 10: rows.append([int(x) for x in v])
    ins = [x for x in rows if t0 <= x[0] <= t1]
    r['nsamp'] = len(ins)
    S = [x[5] for x in ins if x[5] >= 0]
    r['Smax'] = max(S) if S else None
    r['Sdrops'] = sum(1 for a, b in zip(S, S[1:]) if a > 0 and b < 0.75 * a)
    if S:
        k = len(S) // 3
        r['S_first3'] = max(S[:k]) if k else None; r['S_last3'] = max(S[-k:]) if k else None
    per = [x[1] / x[3] for x in ins if x[3] >= 10000 and x[1] >= 0]
    r['c'] = statistics.median(per) if per else None
    r['blocked'] = max((x[7] for x in rows), default=-1)
    r['segbuf'] = max((x[8] for x in rows), default=-1)
    r['heapmax'] = max((x[9] for x in ins), default=-1)
    h0, _ = hist(os.path.join(d, 'hist', 'H0.txt')); r['H0'] = h0
    hs = []
    for f in glob.glob(os.path.join(d, 'hist', 'h-*.txt')):
        ts = int(re.search(r'h-(\d+)', f).group(1))
        tot, cls = hist(f)
        if tot is not None and t0 <= ts <= t1: hs.append((ts, tot - h0, cls))
    hs.sort()
    r['hists'] = hs
    if hs:
        r['peakdH'] = max(x[1] for x in hs)
        mid = (t0 + t1) / 2
        r['dH50'] = min(hs, key=lambda x: abs(x[0] - mid))[1]; r['dH100'] = hs[-1][1]
        pk = [x[2].get('SkinnyPK', (0, 0))[0] for x in hs]
        r['pk'] = pk; r['pkmax'] = max(pk)
        r['pk_last_rising'] = len(pk) > 1 and all(pk[-1] > p for p in pk[:-1])
    return r


def cluster(root, unitcsv):
    u = unit(unitcsv, quiet=True) if unitcsv and os.path.exists(unitcsv) else None
    spec = {'R1': (64, 'sai'), 'R2': (256, 'sai'), 'R3': (64, 'plain'), 'R4': (256, 'plain'), 'R5': (1024, 'sai'), 'R6': (1024, 'plain')}
    R = {}
    for k, (L, kind) in spec.items():
        d = os.path.join(root, k)
        if os.path.exists(os.path.join(d, 'flushes.txt')):
            R[k] = run(d, L * MiB); R[k]['kind'] = kind
    for k, r in R.items():
        L = r['L']
        print(f"{k} L={L // MiB}MiB {r['kind']}: threshold={r['threshold']} partitions={r['partitions']} errors={r['errors']} "
              f"oprate={r['oprate']} dur={r['dur']:.0f}s died={r['died']} oom=[{r['oom']}]")
        print(f"   flushes MEMTABLE_LIMIT={r['flushes']} other={r['other']} Flushing-largest lines={r['ntrig']} (other table {r['trig_other_table']}) "
              f"max Used total={r['usedmax']} blocked={r['blocked']} segBufMax={r['segbuf']} samples={r['nsamp']}")
        if r['Smax'] is not None:
            print(f"   S max={r['Smax']} ({r['Smax'] / L:.3f} L) drops>25%={r['Sdrops']} firstThirdMax={r.get('S_first3')} lastThirdMax={r.get('S_last3')}")
        c = r['c']
        print(f"   ownsCur/ops median={c if c is None else round(c, 1)} B/row; H0={r['H0']} ({r['H0'] / MiB:.1f} MiB); "
              f"heapUsed max={r['heapmax'] / MiB:.0f} MiB")
        if r.get('hists'):
            print(f"   peak dH={r['peakdH'] / MiB:.1f} MiB  dH50={r['dH50'] / MiB:.1f}  dH100={r['dH100'] / MiB:.1f}  SkinnyPK max={r['pkmax']}  "
                  f"(per hist: {r['pk']})")
            for ts, dh, cls in r['hists']:
                print(f"     {ts} dH={dh / MiB:8.1f} MiB  " + ' '.join(f"{n}={cls.get(n, (0, 0))[0]}" for n in ('SkinnyPK', 'PrimaryKeys', 'BufDecKey', 'LongToken')))
    need = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']
    if any(k not in R for k in need):
        print('missing runs:', [k for k in need if k not in R]); return
    f = {k: R[k]['flushes'] for k in need}
    ratio = lambda a, b: f[a] / f[b] if f[b] else float('inf')
    ct = R['R3']['c']; cts = R['R1']['c']
    cs = cts - ct
    pkb = {k: 3 * R[k]['L'] / cts for k in ('R1', 'R2', 'R5')}
    print(f"\nc_t={ct:.1f} B/row (R3); c_t+c_s={cts:.1f} (R1); c_s={cs:.1f}; predicted R1/R3=(c_t+c_s)/c_t={cts / ct:.3f}")
    print('flush ratios: R1/R3=%.3f R1/R2=%.3f R2/R5=%.3f R3/R4=%.3f R4/R6=%.3f' % (
        ratio('R1', 'R3'), ratio('R1', 'R2'), ratio('R2', 'R5'), ratio('R3', 'R4'), ratio('R4', 'R6')))
    pd = {k: R[k].get('peakdH') for k in need}
    print('peak dH MiB: ' + ' '.join(f"{k}={pd[k] / MiB:.1f}" for k in need if pd[k] is not None))
    r_unit = u['r_unit'] if u else float('nan')
    r_cl = (pd['R1'] - pd['R3']) / R['R1']['Smax'] if R['R1']['Smax'] else float('nan')
    print(f'r_cluster=(peak dH R1 - R3)/peak S R1 = {r_cl:.3f}; r_unit={r_unit:.3f}')
    sub = []
    for a, b in (('R1', 'R2'), ('R3', 'R4'), ('R2', 'R5'), ('R4', 'R6')):
        sub.append((f'flushes {a}/{b}={ratio(a, b):.3f} in 4 +- 1.5', 2.5 <= ratio(a, b) <= 5.5))
    rr = ratio('R1', 'R3')
    sub.append((f'R1/R3={rr:.3f} within 25% of (c_t+c_s)/c_t={cts / ct:.3f}', abs(rr / (cts / ct) - 1) <= 0.25))
    sub.append((f'R1/R3={rr:.3f} in 1.3..2.5', 1.3 <= rr <= 2.5)); sub.append((f'R1/R3 > 1.1', rr > 1.1))
    for k in ('R1', 'R2', 'R5'):
        L = R[k]['L']
        sub.append((f'{k} max S <= L/2', R[k]['Smax'] <= L / 2))
        sub.append((f'{k} last-third max S <= 1.2 x first-third max', R[k]['S_last3'] <= 1.2 * R[k]['S_first3']))
        sub.append((f'{k} peak dH <= 2.5 L + 200 MiB ({pd[k] / MiB:.0f} vs {(2.5 * L + 200 * MiB) / MiB:.0f})', pd[k] <= 2.5 * L + 200 * MiB))
        sub.append((f'{k} dH100 - dH50 < 0.5 L', R[k]['dH100'] - R[k]['dH50'] < 0.5 * L))
        sub.append((f'{k} SkinnyPK <= 3 L/(c_t+c_s) = {pkb[k]:.0f} at every histogram (max {R[k]["pkmax"]})', R[k]['pkmax'] <= pkb[k]))
    for k in R:
        sub.append((f'{k} max Used total <= 1.00 ({R[k]["usedmax"]})', R[k]['usedmax'] is not None and R[k]['usedmax'] <= 1.0))
    sub.append((f'peak dH R2/R1={pd["R2"] / pd["R1"]:.3f} in 2..6', 2 <= pd['R2'] / pd['R1'] <= 6))
    sub.append((f'peak dH R5/R2={pd["R5"] / pd["R2"]:.3f} in 2..6', 2 <= pd['R5'] / pd['R2'] <= 6))
    sub.append((f'peak dH R1 - R3 > 0', pd['R1'] > pd['R3']))
    sub.append((f'r_cluster within 30% of r_unit', abs(r_cl / r_unit - 1) <= 0.3 if r_unit == r_unit else False))
    print('\nCluster sub-predictions (B3f + A-K4):')
    for name, ok in sub:
        print(f'  {hm(ok)} {name}')
    # ---- A-K5 decision
    sai, plain = ('R1', 'R2', 'R5'), ('R3', 'R4', 'R6')
    twin = {'R1': 'R3', 'R2': 'R4', 'R5': 'R6'}
    crashed = lambda k: bool(R[k]['died'] or re.search(r':[1-9]', R[k]['oom']) or re.search(r'hs_err: \S', R[k]['oom']))
    incomplete = lambda k: (R[k]['partitions'] < 10_000_000 or R[k]['errors'] > 100_000) and not crashed(k)
    row = None
    if any(R[k]['threshold'] != R[k]['L'] // MiB or R[k]['flushes'] == 0 or incomplete(k) for k in need):
        row = (1, 'Invalid')
    elif any(crashed(k) and not crashed(twin[k]) for k in sai):
        row = (2, 'Refuted - SAI heap escapes the cap (OOM/crash)')
    elif any(R[k]['Smax'] > R[k]['L'] or (R[k]['usedmax'] or 0) > 1.0 for k in sai):
        row = (3, 'Refuted - usage exceeds the limit')
    elif rr <= 1.05:
        row = (4, 'Refuted - SAI charge not reaching the pool')
    elif ((R['R1']['pk'][-1] > 3 * R['R1']['L'] / cts and R['R1']['pk_last_rising'])
          or (R['R1']['dH100'] - R['R1']['dH50'] >= 0.5 * R['R1']['L'] and R['R3']['dH100'] - R['R3']['dH50'] < 0.5 * R['R3']['L'])):
        row = (5, 'Refuted - SAI index retained outside the cap')
    elif ratio('R3', 'R4') < 2 or ratio('R4', 'R6') < 2:
        row = (6, 'Not confirmed - positive control failed')
    elif ratio('R1', 'R2') < 1.5 and pd['R2'] / pd['R1'] < 1.25:
        row = (7, 'Refuted - flat across the knob')
    elif ((pd['R2'] / pd['R1'] < 1.25 and ratio('R1', 'R2') >= 1.5)
          or (R['R1']['dH100'] - R['R1']['dH50'] >= 0.5 * R['R1']['L'] and R['R3']['dH100'] - R['R3']['dH50'] >= 0.5 * R['R3']['L'])):
        row = (8, 'Not confirmed - heap dominated by something else')
    elif (rr > 1.05 and all(R[k]['Smax'] <= R[k]['L'] / 2 and R[k]['Sdrops'] >= 3 and R[k]['dH100'] - R[k]['dH50'] < 0.5 * R[k]['L']
                            and R[k]['pkmax'] <= pkb[k] for k in sai)
          and pd['R2'] / pd['R1'] >= 1.25 and pd['R5'] > pd['R2'] and ratio('R1', 'R2') >= 2 and ratio('R2', 'R5') >= 2):
        row = (9, 'Confirmed - caps')
    else:
        row = (10, 'Not confirmed (no matching row)')
    q = []
    if r_cl > 2 * r_unit: q.append('Qa r_cluster > 2 r_unit')
    if any(R[k]['blocked'] > 0 for k in need): q.append('Qb BlockedOnAllocation > 0 in ' + ','.join(k for k in need if R[k]['blocked'] > 0))
    print(f'\nCLUSTER ROW: {row[0]} {row[1]}; qualifiers: {q or "none"}')


if __name__ == '__main__':
    if sys.argv[1] == 'unit':
        unit(sys.argv[2])
    else:
        cluster(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
