#!/usr/bin/env python3
"""Judge B2f/B2g (with amendments U1-U3) from readings.txt.   usage: unit-analyze.py <readings.txt>
Prints EXPECTED-style PASS/FAIL lines and a SUMMARY line. Exit 0 always (the caller reads SUMMARY)."""
import sys, re, math, collections
R = collections.OrderedDict()
for l in open(sys.argv[1]):
    m = re.match(r'R (\S+) (\S+) (.*)$', l.rstrip('\n'))
    if m: R[(m.group(1), m.group(2))] = m.group(3)
def g(s, k): return R[(s, k)]
res = []
def chk(name, ok, detail): res.append((name, ok, detail)); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)
NS = (3, 7, 15, 31, 40); MS = (2, 4, 8, 16, 32)
unc = {}
for n in NS:
    chk(f'N{n}: {n} live sstables and {n} data files', g('grid', f'N{n}.live') == str(n) and g('grid', f'N{n}.dataFiles') == str(n), f"live={g('grid',f'N{n}.live')} files={g('grid',f'N{n}.dataFiles')}")
    tb = int(g('grid', f'N{n}.totalBytes'))
    for m in MS:
        t = f'N{n}.M{m}'
        exp = min(n, 32) if min(n, 32) >= m else 0
        sret = int(g('grid', t + '.static.returned')); rin = int(g('grid', t + '.real.inputs'))
        chk(f'{t}: static returned {exp}', sret == exp and g('grid', t + '.static.buckets') == '1', f"returned={sret} buckets={g('grid', t+'.static.buckets')}")
        chk(f'{t}: real path inputs {exp}, task null iff empty', rin == exp and (g('grid', t + '.real.taskNull') == 'true') == (exp == 0), f"inputs={rin} taskNull={g('grid', t+'.real.taskNull')}")
        est = math.ceil(n / 32) if n >= m else 0
        chk(f'{t}: estimatedRemaining {est} (A1b: uses both thresholds)', int(g('grid', t + '.real.estimatedRemaining')) == est, f"est={g('grid', t+'.real.estimatedRemaining')}")
        u = int(g('grid', t + '.static.uncompactedBytes')); unc[(n, m)] = u
        chk(f'{t}: uncompacted bytes = total - returned bytes, nothing left to compact when returned = all', u == tb - int(g('grid', t + '.static.returnedBytes')) and (exp == 0) == (u == tb), f'uncompacted={u} total={tb}')
        chk(f'{t}: no sstable lost by the abort', g('grid', t + '.liveAfter') == str(n), g('grid', t + '.liveAfter'))
    seq = [unc[(n, m)] for m in MS]
    chk(f'N{n}: uncompacted bytes non-decreasing in min_threshold (B2f/B2g row 1)', all(a <= b for a, b in zip(seq, seq[1:])), str(seq))
for n in (7, 40):
    for mx in (4, 8, 32):
        t = f'N{n}.max{mx}'; exp = min(n, mx)
        chk(f'control {t}: static and real path return min(N,max)={exp}', int(g('ctl', t + '.static.returned')) == exp and int(g('ctl', t + '.real.inputs')) == exp, f"static={g('ctl', t+'.static.returned')} real={g('ctl', t+'.real.inputs')}")
chk('ovw M8: no task, bytes unchanged (ratio 1.0)', g('ovw', 'M8.real.taskNull') == 'true' and g('ovw', 'M8.bytesAfter') == g('ovw', 'M8.bytesBefore') and g('ovw', 'M8.sstablesAfter') == '7', f"taskNull={g('ovw','M8.real.taskNull')} before={g('ovw','M8.bytesBefore')} after={g('ovw','M8.bytesAfter')}")
r4 = float(g('ovw', 'M4.ratio'))
chk('ovw M4: executed task cuts live bytes to <= 0.25 of before', g('ovw', 'M4.real.taskNull') == 'false' and r4 <= 0.25, f"ratio={r4} before={g('ovw','M4.bytesBefore')} after={g('ovw','M4.bytesAfter')} sstablesAfter={g('ovw','M4.sstablesAfter')}")
chk('instrument: truncate empties the table', g('ovw', 'M4.bytesAfterTruncate') == '0' and g('ovw', 'M8.bytesAfterTruncate') == '0', 'bytesAfterTruncate')
ok = all(r[1] for r in res)
print('SUMMARY', 'ALL PASS' if ok else 'FAILURES: ' + ', '.join(r[0] for r in res if not r[1]))
