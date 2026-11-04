#!/usr/bin/env python3
"""B3f/B3g analysis (amendments A6-A7, 2026-10-26) of the cluster tier of
tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.
usage: cluster-analyze.py <cluster-log-dir> [--shakedown]    writes <dir>/summary.txt and <dir>/readings.csv"""
import csv, json, os, re, statistics, sys

D = sys.argv[1]
PH = json.load(open(D + '/phases.json'))
OUT = open(D + '/summary.txt', 'w')
RES = {'yes': 0, 'no': 0}
MIB, MB = 1 << 20, 1e6
SH = '--shakedown' in sys.argv


def p(s=''):
    print(s); OUT.write(s + '\n')


def ex(desc, c):
    RES['yes' if c else 'no'] += 1
    p(f'EXPECTED: {desc} - {"yes" if c else "NO"}')
    return c


cfg = re.search(r'N=(\d+) NT2=(\d+) NLIVE=(\d+) TS=\[([^\]]*)\] VTS=\[([^\]]*)\] C=(\d+) DUR=(\d+)', open(D + '/session.log').read())
N, NT2, NLIVE = int(cfg.group(1)), int(cfg.group(2)), int(cfg.group(3))
CC, DUR = int(cfg.group(6)), int(cfg.group(7))
p(f'cluster analysis of {D}: N={N} NT2={NT2} NLIVE={NLIVE} C={CC} DUR={DUR}')
reads = list(csv.DictReader(open(D + '/reads.csv')))


def heap(path):
    out = []
    for l in open(path):
        r = l.split()
        if len(r) == 4 and r[0].isdigit():
            out.append(sum(float(x) for x in r[1:]))
    return out


def jfr_buf(path):
    sizes = []
    for r in csv.DictReader(open(path), delimiter='\t'):
        if r['matched'] == 'buf':
            sizes.append(int(r['size']))
    return sizes


def alloc(path):
    m = re.search(r'^(\d+) total=(\d+)', open(path).read()) if os.path.exists(path) else None
    return (int(m.group(1)), int(m.group(2))) if m else None


R = {}                    # (arm, T) -> dict
rows = []
for ph in PH:
    T = ph['T']
    sc = [int(x) for x in open(f'{D}/scanned-{ph["label"]}.txt').read().split()]
    for st in ph['storms']:
        tag, arm = st['tag'], st['arm']
        rd = [r for r in reads if int(r['T']) == T and r['arm'] == arm]
        oc = {}
        for r in rd:
            oc[r['outcome']] = oc.get(r['outcome'], 0) + 1
        idle, storm = heap(f'{D}/heap-idle-{tag}.txt'), heap(f'{D}/heap-storm-{tag}.txt')
        base = min(idle + storm)
        peak = max(storm) - base
        bufs = jfr_buf(f'{D}/jfr-{tag}.tsv')
        i0, a0, a1 = alloc(f'{D}/alloc-idle0-{tag}.txt'), alloc(f'{D}/alloc-before-{tag}.txt'), alloc(f'{D}/alloc-after-{tag}.txt')
        rate = (a0[1] - i0[1]) / (a0[0] - i0[0])                      # background bytes per ms over the idle window (HeapPoll polling included)
        corr = (a1[1] - a0[1]) - rate * (a1[0] - a0[0])               # storm allocation minus background
        a0, a1 = 0, int(corr)
        v = dict(T=T, arm=arm, label=ph['label'], nreads=len(rd), oc=oc, B=max(bufs) if bufs else 0, nbuf=len(bufs), P=peak, base=base,
                 alloc=(a1 - a0) if a0 is not None and a1 is not None else None, A=((a1 - a0) / len(rd)) if rd else 0, rate=rate, scanned=sc, st=st, oom=ph['oom'], warm=ph.get('warm_outcome'))
        R[(arm, ph['label'])] = v
        rows.append(v)
        p(f'  {arm:10s} {ph["label"]:9s}: {len(rd)} reads {oc}; B (largest response-buffer allocation) {v["B"] / MIB:.1f} MiB over {len(bufs)} events; '
          f'heap low {base / MB:.0f} MB, peak rise P {peak / MB:.0f} MB; node alloc {v["alloc"] / MB if v["alloc"] else float("nan"):.0f} MB = {v["A"] / MB:.2f} MB per read (A; background {v["rate"] * 1000 / MB:.1f} MB/s removed); '
          f'TombstoneFailures {st["failures_after"]}; system.log "Scanned over" values (this lifetime) {sorted(set(sc))[:4]}; OOM {ph["oom"]}')
with open(D + '/readings.csv', 'w') as f:
    f.write('arm,label,T,nreads,outcomes,B_bytes,P_bytes,base_bytes,node_alloc_bytes,failures_after\n')
    for v in rows:
        f.write(f'{v["arm"]},{v["label"]},{v["T"]},{v["nreads"]},"{v["oc"]}",{v["B"]},{int(v["P"])},{int(v["base"])},{v["alloc"]},{v["st"]["failures_after"]}\n')

Ts = sorted({v['T'] for v in rows if v['arm'] == 'main'})
main = {v['T']: v for v in rows if v['arm'] == 'main'}
# b1: every main read fails with the tombstone code; the log lines say T+1; the warm-up failed
b1 = ex('b1 every main read at every T fails with the tombstone code (READ_TOO_MANY_TOMBSTONES)',
        all(set(v['oc']) == {'FAIL_TOMBSTONE'} and v['nreads'] > 0 for v in main.values()))
ex('b1b system.log "Scanned over" values are exactly T+1 in each lifetime', all(set(main[T]['scanned']) == {T + 1} for T in Ts))
ex('b1c TombstoneFailures after the main storm = 1 warm-up + the main reads', all(int(float(main[T]['st']['failures_after'])) == 1 + main[T]['nreads'] for T in Ts))
ex('no OutOfMemoryError in any lifetime', not any(v['oom'] for v in rows))
As = [main[T]['A'] for T in Ts]; Bs = [main[T]['B'] for T in Ts]; Ps = [main[T]['P'] for T in Ts]
ratio = lambda a, b: a / b if b else float('inf')
rB = [ratio(As[i + 1], As[i]) for i in range(len(Ts) - 1)]
rJ = [ratio(Bs[i + 1], Bs[i]) for i in range(len(Ts) - 1)]
rP = [ratio(Ps[i + 1], Ps[i]) for i in range(len(Ts) - 1)]
p(f'T values {Ts}; A (node allocation per read) {[round(a / MB, 2) for a in As]} MB, ratios {[round(r, 2) for r in rB]}; JFR B (secondary) {[round(b / MIB, 2) for b in Bs]} MiB, ratios {[round(r, 2) for r in rJ]}; P {[round(x / MB) for x in Ps]} MB; ratios {[round(r, 2) for r in rP]}')
dec = 10.0 if not SH else None
lo, hi = 10 / 3, 30
b2 = ex(f'b2 A(T) (node allocation per read) consecutive ratios in [{lo:.2f}, {hi}] (decade steps, factor 3 of linear)', all(lo <= r <= hi for r in rB))
b3 = ex(f'b3 P(T) strictly increasing, consecutive ratios in [{lo:.2f}, {hi}]', all(a < b for a, b in zip(Ps, Ps[1:])) and all(lo <= r <= hi for r in rP))
equal = ex(f'A(lowest T) and A(highest T) within 25% ({As[-1] / As[0]:.2f})', abs(As[-1] / As[0] - 1) <= 0.25 if As[0] else False)
# size variant
for T in sorted({v['T'] for v in rows if v['arm'] == 'variant'}):
    v = [x for x in rows if x['arm'] == 'variant' and x['T'] == T][0]
    pm_v = v['B'] / (T + 1)
    pm_r = main[T]['B'] / (T + 1)
    p(f'  size variant T={T}: {v["oc"]}, B {v["B"] / MIB:.1f} MiB = {pm_v:.0f} B per marker vs row variant {pm_r:.0f} B per tombstone: ratio {pm_v / pm_r:.1f}')
# controls
live = [v for v in rows if v['arm'] == 'live']
ctl = [v for v in rows if v['arm'] == 'live-1MiB']
if live and ctl:
    lv = [v for v in live if v['T'] == 100000] or live
    off_B, on_B = lv[0]['A'], ctl[0]['A']
    p(f'  live partition (30 MB): unrestricted A {off_B / MB:.1f} MB per read, outcomes {lv[0]["oc"]}; 1 MiB local_read_size_fail: A {on_B / MB:.1f} MB per read, outcomes {ctl[0]["oc"]}')
    cok = ex('control: 1 MiB cap makes the live reads fail (FAIL_READSIZE) and A < 0.8 x unrestricted A',
             set(ctl[0]['oc']) == {'FAIL_READSIZE'} and on_B < 0.8 * off_B)
    ex('negative control: live reads succeed at every T and their A is flat (max/min <= 1.25)',
       all(all(k.startswith('OK') for k in v['oc']) for v in live) and max(v['A'] for v in live) <= 1.25 * min(v['A'] for v in live))
else:
    cok = ex('control arms present', False)
anyok = any(any(k.startswith('OK') for k in v['oc']) for v in main.values())
if not cok:
    row = 'INVALID: positive control did not move (B3g row: control invalid, no conclusion)'
elif anyok:
    row = 'B3g row 3 (a read succeeded with tombstones counted far above T: cap bypassed)'
elif b1 and equal:
    row = 'B3g row 2 (peak/buffer equal at lowest and highest T: not a memory cap)'
elif b1 and b2 and b3:
    row = 'B3g row 1 (heap above baseline scales about linearly with T: claim confirmed)'
elif b1 and b2 and not b3:
    row = 'A7 added row (Not confirmed, partial): per-read buffer follows T, node-level peak does not'
else:
    row = 'Not confirmed (no matching row)'
p(f'MATCHED: {row}; EXPECTED yes={RES["yes"]} NO={RES["no"]}')
