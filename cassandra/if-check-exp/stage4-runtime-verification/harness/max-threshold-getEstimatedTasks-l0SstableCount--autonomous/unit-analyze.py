#!/usr/bin/env python3
"""Judge B2f/B2g (with amendments U3, U4) from readings.txt.   usage: unit-analyze.py <readings.txt>"""
import sys, re, collections
R = collections.OrderedDict()
for l in open(sys.argv[1]):
    m = re.match(r'R (\S+) (\S+) (.*)$', l.rstrip('\n'))
    if m: R[(m.group(1), m.group(2))] = m.group(3)
def g(s, k): return R[(s, k)]
res = []
def chk(name, ok, detail): res.append((name, ok, detail)); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)

l0 = int(g('step2', 'l0SSTables')); live = int(g('step2', 'liveSSTables'))
chk('200 sstables, all in L0', l0 == 200 and live == 200, f'live={live} l0={l0}')
chk('default max_threshold 32, min 4', g('step2', 'defaultMaxThreshold') == '32' and g('step2', 'minThreshold') == '4', f"max={g('step2','defaultMaxThreshold')} min={g('step2','minThreshold')}")
rows = collections.defaultdict(dict)
for (s, k), v in R.items():
    m = re.match(r'(on|off)\.seq(\d+)\.mt(\d+)\.(\w+)$', k)
    if s == 'step3' and m: rows[(m.group(1), int(m.group(2)), int(m.group(3)))][m.group(4)] = v
for mode in ('on', 'off'):
    for (md, seq, mt), d in sorted(rows.items()):
        if md != mode: continue
        exp = (200 // mt) if mode == 'on' else 0
        chk(f'estimate {mode} seq{seq} mt{mt}', int(d['estimate']) == exp and int(d['maxThreshold']) == mt, f"estimate={d['estimate']} expected={exp}")
for key in ('sumOnDiskLength', 'liveDiskSpaceUsed', 'dataFiles'):
    vals = {v[key] for v in rows.values() if key in v}
    chk(f'{key} identical across every setting and mode', len(vals) == 1, str(sorted(vals)))
for mode in ('on', 'off'):
    h = {(s, mt): int(d['heapUsed']) for (md, s, mt), d in rows.items() if md == mode}
    allv = list(h.values()); mean = sum(allv) / len(allv)
    spread = max(allv) - min(allv)
    s32 = [v for (s, mt), v in h.items() if mt == 32]
    noise = max(s32) - min(s32)
    tol = max(0.05 * mean, noise)
    # spread across the three max_threshold values = spread of the per-value means
    means = {mt: sum(v for (s, m2), v in h.items() if m2 == mt) / len([1 for (s, m2) in h if m2 == mt]) for mt in (4, 32, 128)}
    sp = max(means.values()) - min(means.values())
    chk(f'heap spread across values ({mode})', sp <= tol, f'means={ {k: round(v) for k, v in means.items()} } spread={sp:.0f} tol={tol:.0f} (5% mean={0.05*mean:.0f}, noise at 32={noise})')
# controls
b1, b160 = int(g('ctlA', 'size1.estimateByteTermOnly')), int(g('ctlA', 'size160.estimateByteTermOnly'))
chk('control (a): byte term differs by > 50 tasks (size 1 vs 160)', abs(b1 - b160) > 50, f'size1={b1} size160={b160}')
m1, m160 = int(g('ctlB', 'size1.maxOutput')), int(g('ctlB', 'size160.maxOutput'))
chk('control (b): max output file < 1.5 MiB at size 1 and > 10 MiB at size 160', m1 < 1.5 * 1048576 and m160 > 10 * 1048576, f'size1={m1} size160={m160} outputs1={g("ctlB","size1.outputs")} outputs160={g("ctlB","size160.outputs")}')
chk('instrument: truncate empties the table', g('ctlB', 'size1.bytesAfterTruncate') == '0' and g('ctlB', 'size160.bytesAfterTruncate') == '0', 'bytesAfterTruncate')
ok = all(r[1] for r in res)
print('SUMMARY', 'ALL PASS' if ok else 'FAILURES: ' + ', '.join(r[0] for r in res if not r[1]))
