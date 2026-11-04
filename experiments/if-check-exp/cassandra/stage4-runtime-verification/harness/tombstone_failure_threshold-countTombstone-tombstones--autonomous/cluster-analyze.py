#!/usr/bin/env python3
"""B3f/B3g analysis (with audit amendments R4-R6) of the cluster tier of
tombstone_failure_threshold-countTombstone-tombstones--autonomous.
usage: cluster-analyze.py <cluster-log-dir> [<unit tft-unit.tsv>]    writes <dir>/summary.txt and <dir>/readings.csv"""
import csv, glob, json, os, re, statistics, sys

D = sys.argv[1]
UNIT = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser('~/stage4-logs/tft/run1/unit/tft-unit.tsv')
PH = json.load(open(D + '/phases.json'))
OUT = open(D + '/summary.txt', 'w')
RES = {'yes': 0, 'no': 0}
MIB, MB = 1 << 20, 1e6


def p(s=''):
    print(s); OUT.write(s + '\n')


def ex(desc, c):
    RES['yes' if c else 'no'] += 1
    p(f'EXPECTED: {desc} — {"yes" if c else "NO"}')
    return c


cfg = re.search(r'N=(\d+) NLIVE=(\d+) TS=\[([^\]]*)\] CTRL=\[([^\]]*)\] C=(\d+) R=(\d+)', open(D + '/session.log').read())
N, NLIVE = int(cfg.group(1)), int(cfg.group(2))
CC, RR = int(cfg.group(5)), int(cfg.group(6))
NREADS = CC * RR
FULL = N == 200000
# s from the unit tier (R4)
s = 1020.0
try:
    for r in csv.reader(open(UNIT), delimiter='\t'):
        if r[0] == '0' and r[1] == str(2**31 - 1) and int(r[4]) > 0:
            s = int(r[4]) / 30000
except OSError:
    pass
p(f'cluster analysis of {D}: N={N} NLIVE={NLIVE} C={CC} R={RR}; s = {s:.1f} B per tombstone (unit tier, T=MAX)')

reads = list(csv.DictReader(open(D + '/reads.csv')))


def jstat(path):
    out = []                                  # HeapPoll lines (D3): epoch_ms EU OU SU, bytes
    for l in open(path):
        r = l.split()
        if len(r) == 4 and r[0].isdigit():
            out.append((float(r[1]), float(r[2])))
    return out


def jfr(path):
    ev = []
    for r in csv.DictReader(open(path), delimiter='\t'):
        ev.append((r['type'], int(r['size']), r['matched'], r['thread'], r['top']))   # matched: buf / build / -
    return ev


def alloc(path):
    m = re.search(r'total=(\d+)', open(path).read()) if os.path.exists(path) else None
    return int(m.group(1)) if m else None


R = {}
rows = []
for ph in PH:
    T = ph['T']
    sc = [int(x) for x in open(f'{D}/scanned-{ph["label"]}.txt').read().split()]
    gc = open(glob.glob(f'{D}/gc-{ph["label"]}.log*')[0], errors='replace').read() if glob.glob(f'{D}/gc-{ph["label"]}.log*') else ''
    hum = [int(a) for a in re.findall(r'Humongous regions: (\d+)->', gc)]
    for st in ph['storms']:
        tag, pk = st['tag'], st['pk']
        rd = [r for r in reads if int(r['T']) == T and int(r['pk']) == pk]
        oc = {}
        for r in rd:
            oc[r['outcome']] = oc.get(r['outcome'], 0) + 1
        idle, storm = jstat(f'{D}/jstat-idle-{tag}.txt'), jstat(f'{D}/jstat-storm-{tag}.txt')
        base = statistics.median(e + o for e, o in idle)
        baseo = statistics.median(o for e, o in idle)
        rise = max(e + o for e, o in storm) - base
        riseo = max(o for e, o in storm) - baseo
        ev = jfr(f'{D}/jfr-{tag}.tsv')
        dob = [e for e in ev if e[2] == 'buf']     # response-buffer growth (DataOutputBuffer.expandToFit in the stack)
        maxbuf = max([e[1] for e in dob], default=0)
        sum_out = sum(e[1] for e in dob if e[0] == 'ObjectAllocationOutsideTLAB')
        other = max([e[1] for e in ev if e[2] != 'buf'], default=0)
        a0, a1 = alloc(f'{D}/alloc-before-{tag}.txt'), alloc(f'{D}/alloc-after-{tag}.txt')
        node_per_read = (a1 - a0) / len(rd) if a0 is not None and a1 is not None and rd else float('nan')
        fails = None
        try:
            fails = int(float(st['failures_after'])) - int(float(ph['failures_after_warmup']))
        except (ValueError, KeyError):
            pass
        x = dict(T=T, pk=pk, reads=len(rd), outcomes=oc, maxbuf=maxbuf, n_dob=len(dob), jfr_per_read=sum_out / max(len(rd), 1),
                 other_max=other, rise=rise, rise_old=riseo, base=base, node_per_read=node_per_read,
                 scanned_lines=len(sc), scanned_set=sorted(set(sc)), fails_delta=fails if pk == 0 else None,
                 hist_max=st.get('scanned_hist_max'), humongous_max=max(hum, default=0), storm_s=(st['end_ms'] - st['start_ms']) / 1000,
                 oom=ph.get('oom'), T_read=ph.get('T_read'))
        R[(T, pk)] = x
        rows.append(x)
        p(f'T={T} pk={pk}: reads {len(rd)} {oc}; storm {x["storm_s"]:.1f} s; T read back {x["T_read"]}; '
          f'"Scanned over" lines {len(sc)} values {x["scanned_set"][:5]}; TombstoneFailures +{fails} (storm); hist Max {x["hist_max"]}')
        p(f'   JFR dob events {len(dob)}, max buffer {maxbuf/MB:.2f} MB ({maxbuf/MIB:.2f} MiB), out-of-TLAB sum/read {x["jfr_per_read"]/MB:.2f} MB, '
          f'largest other alloc {other/MB:.2f} MB; node alloc/read (R5) {node_per_read/MB:.2f} MB')
        p(f'   heap: idle median EU+OU {base/MB:.0f} MB; peak rise EU+OU {rise/MB:.0f} MB, OU {riseo/MB:.0f} MB; '
          f'gc.log max humongous regions {x["humongous_max"]} (x16 MiB = {x["humongous_max"]*16} MiB); OOM {x["oom"]}')
with open(D + '/readings.csv', 'w') as f:
    w = csv.writer(f)
    keys = ['T', 'pk', 'reads', 'outcomes', 'maxbuf', 'n_dob', 'jfr_per_read', 'node_per_read', 'rise', 'rise_old', 'base',
            'scanned_lines', 'scanned_set', 'fails_delta', 'hist_max', 'humongous_max', 'other_max', 'storm_s']
    w.writerow(keys)
    for x in rows:
        w.writerow([x[k] if k != 'scanned_set' else ' '.join(map(str, x[k][:5])) for k in keys])

Ts = sorted(t for (t, pk) in R if pk == 0)
below = [t for t in Ts if t < N]; above = [t for t in Ts if t >= N]
ref, top = above[0], above[-1]
g = lambda t, k, pk=0: R[(t, pk)][k]
p('\n-- R4 decisive criteria (B3g row 1)')
a1 = all(g(t, 'outcomes').get('FAIL_TOMBSTONE', 0) == NREADS == g(t, 'reads') for t in below)
a2 = all(g(t, 'scanned_set') == [t + 1] and g(t, 'scanned_lines') >= NREADS for t in below)
a3 = all(g(t, 'outcomes').get('OK:0', 0) == NREADS == g(t, 'reads') for t in above)
A = ex(f'(a) T<N: all {NREADS} reads fail with READ_TOO_MANY_TOMBSTONES', a1) & \
    ex('(a) T<N: every "Scanned over" line says T+1 (and >= one per read)', a2) & \
    ex(f'(a) T>=N: all {NREADS} reads succeed with 0 rows', a3)
order = below + [ref]
b1 = all(g(x, 'maxbuf') < g(y, 'maxbuf') for x, y in zip(order, order[1:]))
b2 = all(abs(g(t, 'maxbuf') / g(ref, 'maxbuf') - 1) <= 0.15 for t in above[1:])
b3 = all(g(t, 'maxbuf') <= 2.2 * s * (t + 1) for t in below)
B = ex('(b) max buffer strictly ordered ' + ' < '.join(f'{g(t,"maxbuf")/MB:.2f}' for t in order) + ' MB', b1) & \
    ex('(b) max buffer at T>N within +-15% of T=' + str(ref) + ' (' + ', '.join(f'{g(t,"maxbuf")/g(ref,"maxbuf"):.3f}' for t in above[1:]) + ')', b2) & \
    ex('(b) failing T: max buffer <= 2.2 x s x (T+1) (' + ', '.join(f'{g(t,"maxbuf")/(s*(t+1)):.2f}' for t in below) + ' x s(T+1))', b3)
c1 = all(g(x, 'rise_old') < g(y, 'rise_old') for x, y in zip(order, order[1:]))   # D2: OU peak rise
c2 = all(abs(g(t, 'rise_old') / g(ref, 'rise_old') - 1) <= 0.15 for t in above[1:])
Cc = ex('(c, D2) OU peak rise strictly ordered ' + ' < '.join(f'{g(t,"rise_old")/MB:.0f}' for t in order) + ' MB', c1) & \
     ex('(c, D2) OU peak rise at T>N within +-15% of T=' + str(ref) + ' (' + ', '.join(f'{g(t,"rise_old")/g(ref,"rise_old"):.3f}' for t in above[1:]) + ')', c2)
ctrl = sorted(t for (t, pk) in R if pk == 1)
Dd = True
if len(ctrl) == 2:
    lo, hi = ctrl
    for k in ('maxbuf', 'rise_old'):
        u, v = g(lo, k, 1), g(hi, k, 1)
        Dd &= ex(f'(d) live control {k} at T={lo} vs T={hi}: {u/MB:.2f} vs {v/MB:.2f} MB within +-15% or both < 4 MiB',
                 (bool(v) and abs(u / v - 1) <= 0.15) or (u < 4 * MIB and v < 4 * MIB))
    Dd &= ex(f'(d) live control: all reads succeed with {NLIVE} rows at both T',
             all(g(t, 'outcomes', 1).get(f'OK:{NLIVE}', 0) == g(t, 'reads', 1) == NREADS for t in ctrl))
p('\n-- B3f sub-predictions (reported, not decisive)')
if FULL:
    band = {1000: (0, 2 * MB), 20000: (20 * MB, 41 * MB), 100000: (102 * MB, 205 * MB), 300000: (204 * MB, 410 * MB), 1000000: (204 * MB, 410 * MB)}
    rb = {1000: (0, 0.1e9), 20000: (0.16e9, 0.5e9), 100000: (0.8e9, 2.4e9), 300000: (1.6e9, 4.9e9), 1000000: (1.6e9, 4.9e9)}
    for t in Ts:
        lo, hi = band[t]; ex(f'sub: T={t} max buffer {g(t,"maxbuf")/MB:.2f} MB in {lo/MB:.0f}-{hi/MB:.0f} MB', lo <= g(t, 'maxbuf') <= hi)
    for t in Ts:
        lo, hi = rb[t]; ex(f'sub: T={t} peak-heap rise {g(t,"rise")/1e9:.3f} GB in {lo/1e9:.2f}-{hi/1e9:.2f} GB', lo <= g(t, 'rise') <= hi)
    for t in below:
        ex(f'sub: T={t} TombstoneFailures +{g(t,"fails_delta")} = {NREADS}', g(t, 'fails_delta') == NREADS)
    for t in above:
        hm = float(g(t, 'hist_max')) if not str(g(t, 'hist_max')).startswith('ERR') else -1
        ex(f'sub: T={t} TombstoneScannedHistogram Max {hm:.0f} = {N} (histogram bucket: N <= Max <= 1.25 N)', N <= hm <= 1.25 * N)
    for name, k in (('JFR out-of-TLAB sum/read', 'jfr_per_read'), ('node alloc/read (R5)', 'node_per_read')):
        r1 = g(20000, k) / g(1000, k) if g(1000, k) else float('inf')
        r2 = g(100000, k) / g(20000, k) if g(20000, k) else float('inf')
        r3 = g(1000000, k) / g(300000, k) if g(300000, k) else float('inf')
        ex(f'sub: {name} 20k:1k = {r1:.2f} in 14-26', 14 <= r1 <= 26)
        ex(f'sub: {name} 100k:20k = {r2:.2f} in 3.5-6.5', 3.5 <= r2 <= 6.5)
        ex(f'sub: {name} 1M:300k = {r3:.2f} in 0.85-1.15', 0.85 <= r3 <= 1.15)
oom = any(x['oom'] for x in rows)
ex('sub: no OutOfMemoryError in any lifetime', not oom)
extra = [t for t in Ts if g(t, 'rise_old') > CC * 3 * s * min(t + 1, N)]
p(f'peak rise above C x 3 x content at T = {extra} (B3g row 5 if non-empty)')
p('\n-- row decision')
if not a1 and any(g(t, 'outcomes').get('OK:0', 0) for t in below):
    row = 'B3g row 3 (reads succeed at T < N: constraint not applied; not tested)'
elif A and B and Cc and Dd:
    row = 'B3g row 1 (Confirmed: the threshold governs the replica on-heap response memory)'
elif A and g(below[0], 'maxbuf') >= 0.85 * g(top, 'maxbuf'):
    row = 'B3g row 2 (Refuted: the abort does not prevent the allocation)'
elif g(top, 'humongous_max') == 0 and g(top, 'rise_old') <= g(below[0], 'rise_old'):
    row = 'B3g row 4 (positive control did not move: Not confirmed)'
elif A and B and not Cc:
    row = 'B3g R6 row (per-read cap confirmed, node-level peak not shown: Not confirmed (partial))'
elif A and not B:
    row = 'B3g R6 row (buffers do not follow: Not confirmed)'
else:
    row = 'no single row (see the NO lines; e.g. the live control (d))'
p(f'MATCHED: {row}; extra-consumer note: {"yes" if extra else "no"}; OOM: {oom}; EXPECTED yes={RES["yes"]} NO={RES["no"]}')
