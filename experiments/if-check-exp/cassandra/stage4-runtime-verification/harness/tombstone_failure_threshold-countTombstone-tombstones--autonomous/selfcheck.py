#!/usr/bin/env python3
"""Independent self-check of run 1 of tombstone_failure_threshold-countTombstone-tombstones--autonomous.
usage (on the run node): selfcheck.py <unit-dir> <cluster-dir> <RUN dir with jfr/ and client/>
It does not read summary.txt, readings.csv, tft-unit.tsv or the jfr-*.tsv files the run scripts wrote. It re-parses:
  unit:    the TFT lines in the test JVM's own log (test.log) and the junit XML's counts, and recomputes B2g row 1 (R4) from them;
  cluster: the cqlsh output of every storm read (client/), the system-<T>.log segments (ERROR lines and the startup
           config dump), the raw .jfr files through the JDK's own `jfr print --json` (not JfrBuf), the HeapPoll sample
           files, the gc-<T>.log humongous lines, the ThreadAlloc files; phases.json is used only for the T list.
Prints one line per check: ok / FAIL, then the counts."""
import glob, json, os, re, statistics, subprocess, sys

U, D, RUN = sys.argv[1], sys.argv[2], sys.argv[3]
RES = {'ok': 0, 'FAIL': 0}
MB = 1e6


def chk(desc, c):
    RES['ok' if c else 'FAIL'] += 1
    print(f'{"ok  " if c else "FAIL"} {desc}')
    return c


# ---------------- unit
xml = open(glob.glob(U + '/TEST-*.xml')[0], errors='replace').read()
tlog = open(U + '/test.log', errors='replace').read()      # the test JVM's own log (System.out goes through the logger)
lines = sorted(set(re.findall(r'\[main\] \S+ TFT (\d+)\t(\d+)\t(\w+)\t(-?\d+)\t(-?\d+)\t(-?\d+)\t(\d+)\t(\d+)\t(\d+)', tlog)))
u = {(int(l[0]), int(l[1])): dict(out=l[2], cnt=int(l[3]), rb=int(l[4]), unf=int(l[5]), a=int(l[6])) for l in lines}
print(f'unit: {len(u)} TFT records from the test JVM log (test.log)')
chk('unit: 14 records (2 pk x 7 T)', len(u) == 14)
NU, MAX = 30000, 2**31 - 1
Ts = sorted({t for _, t in u})
chk('unit: pk0 TOE exactly for T < 30000, count T+1', all((u[(0, t)]['out'] == 'TOE') == (t < NU) and (t >= NU or u[(0, t)]['cnt'] == t + 1) for t in Ts))
A = lambda t, pk=0: u[(pk, t)]['a']
low = [t for t in Ts if t < NU]
chk('unit: A strictly increasing for T < N: ' + ', '.join(f'{A(t)/MB:.2f}' for t in low), all(A(x) < A(y) for x, y in zip(low, low[1:])))
chk(f'unit: A(1000)/A(MAX) = {A(1000)/A(MAX):.4f} <= 0.10', A(1000) <= 0.10 * A(MAX))
chk('unit: A(29999), A(30000), A(100000) within 10% of A(MAX)', all(abs(A(t) / A(MAX) - 1) <= 0.10 for t in (29999, 30000, 100000)))
chk('unit: OK reads hold 30000 unfiltered', all(v['unf'] == NU for v in u.values() if v['out'] == 'OK'))
p1 = [A(t, 1) for t in Ts]
chk(f'unit: pk1 all OK, max/min {max(p1)/min(p1):.3f} <= 1.10', all(u[(1, t)]['out'] == 'OK' for t in Ts) and max(p1) / min(p1) <= 1.10)
s = u[(0, MAX)]['rb'] / NU
print(f'unit: s = {s:.1f} B; A(10k)/A(1k) = {A(10000)/A(1000):.2f} (band 7-13); A(20k)/A(10k) = {A(20000)/A(10000):.2f}')
chk('unit: junit reports Tests run: 1, Failures: 0, Errors: 0', re.search(r'tests="1"', xml) is not None and 'errors="0"' in xml and 'failures="0"' in xml)

# ---------------- cluster
ph = json.load(open(D + '/phases.json'))
TS = sorted(p['T'] for p in ph)
N, NLIVE, NR = 200000, 20000, 40
sess = open(D + '/session.log').read()
R = {}
for p in ph:
    T, lab = p['T'], p['label']
    seg = open(f'{D}/system-{lab}.log', errors='replace').read()
    m = re.search(r'tombstone_failure_threshold=(\d+)', seg)
    chk(f'T={T}: node config dump says tombstone_failure_threshold={m.group(1) if m else None}', m is not None and int(m.group(1)) == T)
    chk(f'T={T}: read back by sjk in session.log', re.search(rf'T confirmed by sjk: {T}\b', sess) is not None)
    err = [int(x) for x in re.findall(r'^ERROR .*Scanned over (\d+) tombstones', seg, re.M)]
    chk(f'T={T}: no java.lang.OutOfMemoryError in system.log', 'java.lang.OutOfMemoryError' not in seg)
    gc = ''.join(open(f, errors='replace').read() for f in glob.glob(f'{D}/gc-{lab}.log*'))
    hum = max([int(a) for a in re.findall(r'Humongous regions: (\d+)->', gc)], default=0)
    for pk in ([0, 1] if os.path.exists(f'{D}/jstat-storm-T{T}-pk1.txt') else [0]):
        tag = f'T{T}-pk{pk}'
        outs = [open(f, errors='replace').read() for f in sorted(glob.glob(f'{RUN}/client/c_{tag}_*.out'))]
        nf = sum(1 for o in outs if 'READ_TOO_MANY_TOMBSTONES' in o)
        rows = [int(x.group(1)) for o in outs for x in [re.search(r'\((\d+) rows\)', o)] if x]
        # JFR through the JDK tool
        jf = f'{RUN}/jfr/{tag}.jfr'
        js = subprocess.run(['jfr', 'print', '--json', '--stack-depth', '8', '--events', 'ObjectAllocationOutsideTLAB,ObjectAllocationInNewTLAB', jf],
                            capture_output=True, text=True).stdout
        maxbuf = 0
        try:
            evs = json.loads(js)['recording']['events']
        except Exception:
            evs = []
        for e in evs:
            fr = e['values'].get('stackTrace', {}) or {}
            frames = fr.get('frames', [])
            if any(f['method']['name'] == 'expandToFit' and f['method']['type']['name'].endswith('DataOutputBuffer') for f in frames):
                maxbuf = max(maxbuf, int(e['values']['allocationSize']))
        idle = [tuple(map(int, l.split()[1:3])) for l in open(f'{D}/jstat-idle-{tag}.txt') if l.split() and l.split()[0].isdigit()]
        st = [tuple(map(int, l.split()[1:3])) for l in open(f'{D}/jstat-storm-{tag}.txt') if l.split() and l.split()[0].isdigit()]
        ou_rise = max(o for e, o in st) - statistics.median(o for e, o in idle)
        all_rise = max(e + o for e, o in st) - statistics.median(e + o for e, o in idle)
        a0 = int(re.search(r'total=(\d+)', open(f'{D}/alloc-before-{tag}.txt').read()).group(1))
        a1 = int(re.search(r'total=(\d+)', open(f'{D}/alloc-after-{tag}.txt').read()).group(1))
        R[(T, pk)] = dict(n=len(outs), nf=nf, rows=rows, maxbuf=maxbuf, ou=ou_rise, all=all_rise, alloc=(a1 - a0) / max(len(outs), 1),
                          err=err, hum=hum, nev=len(evs), samples=len(st))
        print(f'{tag}: reads {len(outs)} fail {nf} rows {sorted(set(rows))}; jfr events {len(evs)} max expandToFit alloc {maxbuf/MB:.2f} MB; '
              f'OU rise {ou_rise/MB:.0f} MB, EU+OU rise {all_rise/MB:.0f} MB ({len(st)} samples); node alloc/read {(a1-a0)/max(len(outs),1)/MB:.1f} MB; '
              f'ERROR "Scanned over" lines {len(err)} {sorted(set(err))}; humongous max {hum}')
below = [t for t in TS if t < N]; above = [t for t in TS if t >= N]
for t in below:
    r = R[(t, 0)]
    chk(f'(a) T={t}: {r["nf"]}/{r["n"]} reads failed with READ_TOO_MANY_TOMBSTONES (expect 40/40)', r['n'] == NR and r['nf'] == NR)
    chk(f'(a) T={t}: {len(r["err"])} ERROR lines, all "Scanned over {t+1}" (>= 41 incl. warm-up)', len(r['err']) >= NR + 1 and set(r['err']) == {t + 1})
    chk(f'(b) T={t}: max buffer {r["maxbuf"]/MB:.2f} MB <= 2.2 x s x (T+1) = {2.2*s*(t+1)/MB:.2f} MB', 0 < r['maxbuf'] <= 2.2 * s * (t + 1) or (r['maxbuf'] == 0 and t * s < 1 << 20))
for t in above:
    r = R[(t, 0)]
    chk(f'(a) T={t}: 40 reads OK with 0 rows, no ERROR line', r['n'] == NR and r['nf'] == 0 and r['rows'].count(0) == NR and not r['err'])
order = below + [above[0]]
chk('(b) max buffer ordered ' + ' < '.join(f'{R[(t,0)]["maxbuf"]/MB:.2f}' for t in order), all(R[(x, 0)]['maxbuf'] < R[(y, 0)]['maxbuf'] for x, y in zip(order, order[1:])))
chk('(b) max buffer at 1M within 15% of 300k', all(abs(R[(t, 0)]['maxbuf'] / R[(above[0], 0)]['maxbuf'] - 1) <= 0.15 for t in above[1:]))
chk('(c) OU rise ordered ' + ' < '.join(f'{R[(t,0)]["ou"]/MB:.0f}' for t in order), all(R[(x, 0)]['ou'] < R[(y, 0)]['ou'] for x, y in zip(order, order[1:])))
chk('(c) OU rise at 1M within 15% of 300k', all(abs(R[(t, 0)]['ou'] / R[(above[0], 0)]['ou'] - 1) <= 0.15 for t in above[1:]))
ct = sorted(t for t, pk in R if pk == 1)
if len(ct) == 2:
    x, y = R[(ct[0], 1)], R[(ct[1], 1)]
    for k in ('maxbuf', 'ou'):
        chk(f'(d) control {k}: {x[k]/MB:.2f} vs {y[k]/MB:.2f} MB (15% or both < 4 MiB)', (y[k] and abs(x[k] / y[k] - 1) <= 0.15) or (x[k] < 4 << 20 and y[k] < 4 << 20))
    chk(f'(d) control: all 80 reads returned {NLIVE} rows', x['rows'].count(NLIVE) == NR and y['rows'].count(NLIVE) == NR)
chk('positive control: T=1M max buffer > 100 x T=1k max buffer', R[(above[-1], 0)]['maxbuf'] > 100 * max(R[(below[0], 0)]['maxbuf'], 1))
left = subprocess.run("ps -eo pid,args | grep -E '^ *[0-9]+ [^ ]*java .*CassandraDaemon' | grep -v grep", shell=True, capture_output=True, text=True).stdout
chk('no CassandraDaemon left', left.strip() == '')
print(f'SELF-CHECK: {RES["ok"]} ok, {RES["FAIL"]} FAIL')
