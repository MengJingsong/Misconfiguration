#!/usr/bin/env python3
"""Cluster-tier analysis for commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous (B3f; B3g as amended R3).
Usage: python3 -I analyze_cluster.py <run1/cluster dir>
Reads raw files only: <arm>/du.csv, jmx.csv, times.txt, system.log (flush lines, UTC timestamps), debug.log.gz (segment
deletions), stress.out. Does not read counts.txt / flushes.txt. Windows: write = [T0, T1], run = [T0, TS] (TS = settle end)."""
import gzip, os, re, sys
from datetime import datetime, timezone

MiB = 1 << 20; S = 32 * MiB; DIRENT = 4096
D = sys.argv[1]
ok_n = [0, 0]
def exp(desc, cond):
    ok_n[0 if cond else 1] += 1
    print(f"EXPECTED: {desc}: {'yes' if cond else 'NO'}")

TS_RE = re.compile(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3})')
def ms(line):
    m = TS_RE.search(line)
    if not m: return None
    dt = datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000) + int(m.group(2))

def arm(cap):
    d = os.path.join(D, str(cap))
    t = dict(re.findall(r'(\w+)=(\d+)', open(os.path.join(d, 'times.txt')).read()))
    T0, T1, TS = int(t['T0']), int(t['T1']), int(t['TS'])
    du = []
    for line in open(os.path.join(d, 'du.csv')):
        p = line.strip().split(',')
        if len(p) < 3 or not p[1].isdigit(): continue
        du.append((int(p[0]), int(p[1]) - DIRENT, int(p[2])))
    jmx = []
    for line in open(os.path.join(d, 'jmx.csv')):
        p = line.strip().split(',')
        if len(p) == 2 and p[1].isdigit(): jmx.append((int(p[0]), int(p[1])))
    fl = []
    for line in open(os.path.join(d, 'system.log'), errors='replace'):
        m = re.search(r'Enqueuing flush of (\S+?), Reason: (\w+)', line)
        if m: fl.append((ms(line), m.group(1), m.group(2)))
    dels = []
    with gzip.open(os.path.join(d, 'debug.log.gz'), 'rt', errors='replace') as f:
        for line in f:
            if 'is no longer active and will be deleted' in line: dels.append(ms(line))
    so = open(os.path.join(d, 'stress.out'), errors='replace').read()
    tot = re.search(r'Total partitions\s*:\s*([\d,]+)', so); err = re.search(r'Total errors\s*:\s*([\d,]+)', so)
    rate = re.search(r'Op rate\s*:\s*([\d,]+)', so)
    run = [x for x in du if T0 <= x[0] <= TS]
    pk = max(run, key=lambda x: x[1])
    settled = [x for x in du if x[0] <= TS][-1]
    wr = [x for x in du if T0 <= x[0] <= T1]
    endw = wr[-1] if wr else None
    cld = [f for f in fl if f[1] == 'keyspace1.standard1' and f[2] == 'COMMITLOG_DIRTY' and T0 <= f[0] <= TS]
    cldw = [f for f in cld if f[0] <= T1]
    ml = [f for f in fl if f[1] == 'keyspace1.standard1' and f[2] == 'MEMTABLE_LIMIT' and T0 <= f[0] <= TS]
    other = sorted(set((f[1], f[2]) for f in fl if T0 <= f[0] <= TS and f[2] != 'COMMITLOG_DIRTY'))
    delw = [x for x in dels if T0 <= x <= TS]
    jrun = [x for x in jmx if T0 <= x[0] <= TS]
    jpk = max(x[1] for x in jrun) if jrun else None
    filediff = max(abs(x[1] - x[2] * S) for x in run)
    nfd = sum(1 for x in run if abs(x[1] - x[2] * S) > 0)
    falls = sum(1 for a, b in zip(run, run[1:]) if b[1] < a[1])
    # B3d/B2g "falls back": settled <= T + S
    r = dict(cap=cap, T0=T0, T1=T1, TS=TS, peak=pk[1], peakT=(pk[0] - T0) / 1000, settled=settled[1], endw=endw[1] if endw else None,
             cld=len(cld), cldw=len(cldw), cld_before_peak=sum(1 for f in cld if f[0] <= pk[0]), ml=len(ml), other=other,
             dels=len(delw), jpk=jpk, jn=len(jrun), filediff=filediff, nfd=nfd, falls=falls, n=len(run),
             tot=tot.group(1) if tot else None, err=err.group(1) if err else None, rate=rate.group(1) if rate else None,
             wsec=(T1 - T0) / 1000, cldtimes=[round((f[0] - T0) / 1000, 1) for f in cld],
             deltimes=[round((x - T0) / 1000, 1) for x in delw])
    print(f"ARM {cap}: stress partitions={r['tot']} errors={r['err']} rate={r['rate']} op/s write={r['wsec']:.1f}s samples={r['n']} | "
          f"peak={r['peak']/MiB:.0f}MiB at +{r['peakT']:.1f}s, end-of-write={r['endw']/MiB:.0f}, settled={r['settled']/MiB:.0f} | "
          f"JMX peak={(jpk or 0)/MiB:.0f}MiB ({r['jn']} samples) | CLD standard1={r['cld']} (in write {r['cldw']}, before peak {r['cld_before_peak']}) "
          f"ML={r['ml']} | segment deletions={r['dels']} | du falls={r['falls']} | max|du-32MiB*files|={filediff/MiB:.0f}MiB in {nfd} samples")
    print(f"   CLD at +s {r['cldtimes']}")
    print(f"   deletions at +s {r['deltimes'][:60]}")
    print(f"   other flush reasons in run window: {other}")
    return r

A = {c: arm(c) for c in [8192, 128, 256, 512]}
ctrl = A[8192]
print("\n== B3f")
for T, lo in [(128, 5), (256, 3), (512, 1)]:
    a = A[T]
    exp(f"{T}: peak {a['peak']/MiB:.0f} <= T+4S = {T+128} MiB", a['peak'] <= (T + 128) * MiB)
    exp(f"{T}: settled {a['settled']/MiB:.0f} <= T", a['settled'] <= T * MiB)
    exp(f"{T}: COMMITLOG_DIRTY {a['cld']} >= {lo}", a['cld'] >= lo)
exp(f"control peak {ctrl['peak']/MiB:.0f} MiB in 1.0-1.1 GiB", 1024 * MiB <= ctrl['peak'] <= 1126 * MiB)
exp(f"control settled ~ peak ({ctrl['settled']/MiB:.0f} vs {ctrl['peak']/MiB:.0f})", ctrl['settled'] >= ctrl['peak'] - S)
exp(f"control COMMITLOG_DIRTY 0 ({ctrl['cld']})", ctrl['cld'] == 0)
ov = [A[T]['peak'] / MiB - T for T in (128, 256, 512)]
exp(f"peak - T about the same across 128/256/512: {ov}", max(ov) - min(ov) <= 2 * 32)
for c in A:
    exp(f"{c}: du within one segment of 32 MiB x files", A[c]['filediff'] <= S)
    exp(f"{c}: MEMTABLE_LIMIT 0 ({A[c]['ml']})", A[c]['ml'] == 0)

print("\n== B3g rows (R3), in order")
binding = [128, 256, 512]
peaks = [A[T]['peak'] for T in binding]
follows = peaks == sorted(peaks) and all(p < 0.8 * ctrl['peak'] for p in peaks)
fell = {T: A[T]['settled'] <= (T + 32) * MiB for T in binding}
print(f"peaks {[p/MiB for p in peaks]} MiB; control {ctrl['peak']/MiB:.0f}; 0.8*control {0.8*ctrl['peak']/MiB:.0f}; follows T: {follows}; fell back: {fell}")
if ctrl['peak'] < 512 * MiB: row = '5 Invalid'
elif any(A[c]['ml'] for c in A): row = '6 Invalid'
elif any(A[T]['jpk'] is not None and A[T]['jpk'] <= (T + 128) * MiB and A[T]['peak'] > A[T]['jpk'] + 2 * S for T in binding): row = '3 Refuted for disk'
elif any(A[T]['peak'] >= 0.8 * ctrl['peak'] and (A[T]['cld_before_peak'] == 0 or not fell[T]) for T in binding): row = '2 Refuted'
elif any(A[T]['peak'] >= 0.8 * ctrl['peak'] and A[T]['cldw'] > 0 and fell[T] for T in binding): row = '4b Not confirmed (bypass)'
elif follows and all(fell.values()) and any(A[T]['cld'] == 0 for T in binding): row = '9 Not confirmed'
elif (not follows) and all(p < 0.8 * ctrl['peak'] for p in peaks) and all(A[T]['settled'] <= T * MiB and A[T]['cld'] >= 1 for T in binding) \
        and ctrl['cld'] == 0: row = '4c Not confirmed (peak set by flush throughput, not T) - caps (soft)'   # added 2026-10-21 after attempt 1
else:
    base = follows and all(A[T]['settled'] <= T * MiB and A[T]['cld'] >= 1 for T in binding) and ctrl['cld'] == 0
    strict = base and all(A[T]['peak'] <= (T + 128) * MiB for T in binding) and max(ov) - min(ov) <= 64
    row = '1 Confirmed' if strict else ('4a Confirmed (missed sub-predictions)' if base else 'no row')
print(f"CLUSTER B3g ROW: {row}")
print(f"\nTOTAL EXPECTED yes={ok_n[0]} NO={ok_n[1]}")
