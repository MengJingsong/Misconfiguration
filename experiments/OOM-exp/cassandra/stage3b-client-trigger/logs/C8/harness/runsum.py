#!/usr/bin/env python3
"""C8 stage 3-b confirm (2026-11-24): runsum.py <run dir>: one summary per attack lifetime, from driver.txt, gauges.csv
(C8Sampler), gc.log*, system.log*, debug.log*, stdout.txt, stress.log, create-index.out. GC parsing as stage 2's selfcheck.py."""
import glob, os, re, sys
from datetime import datetime, timezone
R = sys.argv[1]; MiB = 2 ** 20


def rd(pat):
    return '\n'.join(open(f, errors='replace').read() for f in sorted(glob.glob(os.path.join(R, pat))))


drv = rd('driver.txt')
a0 = int(re.search(r'attack start at_ms (\d+)', drv).group(1))
ci = re.search(r'CREATE INDEX \(as attacker\) issued at_ms (\d+)', drv)
ci = int(ci.group(1)) if ci else None
gone = re.search(r'daemon gone while attack running at_ms (\d+)', drv)
end = re.search(r'endpoint (\S+)', drv)
print('endpoint:', end.group(1) if end else '?', '| END line:', (re.search(r'END (.*)', drv) or [None, '?'])[1])
if gone:
    print('daemon gone at %+.1f s from attack start (%+.1f s from CREATE INDEX)' % ((int(gone.group(1)) - a0) / 1000, (int(gone.group(1)) - ci) / 1000 if ci else float('nan')))
print('create-index.out:', ' | '.join(l.strip() for l in open(os.path.join(R, 'create-index.out'), errors='replace') if l.strip() and 'password' not in l.lower() and 'credentials' not in l.lower()) if os.path.exists(os.path.join(R, 'create-index.out')) else '-')
rows = []
for l in open(os.path.join(R, 'gauges.csv')):
    p = l.strip().split(',')
    if len(p) >= 13 and p[0].isdigit():
        rows.append([int(x) for x in p])
if rows:
    k1 = max(r[1] for r in rows); hu = max(r[4] for r in rows)
    last = rows[-1]
    print('gauges: samples %d; K_D1 peak %.0f MiB; limit %s; heap used peak %.0f MiB; blocked-on-allocation max %d; key cache K max %.1f MB / %d entries' % (
        len(rows), k1 / MiB, sorted({r[2] for r in rows if r[2] > 0}), hu / MiB, max(r[7] for r in rows), max(r[11] for r in rows) / 1e6, max(r[12] for r in rows)))
    print('last sample at %+.1f s from attack start: K_D1 %.0f MiB, heap used %.0f MiB, builds in progress %d, AllMemtablesOnHeap %.0f MiB, key cache %d entries' % (
        (last[0] - a0) / 1000, last[1] / MiB, last[4] / MiB, last[3], last[6] / MiB, last[12]))
    b = [r for r in rows if r[3] > 0]
    if b:
        print('builds in progress from %+.1f s to %+.1f s (from attack start)' % ((b[0][0] - a0) / 1000, (b[-1][0] - a0) / 1000))
gc = rd('gc.log*')
pg, pauses = [], []
for m in re.finditer(r'^\[([^\]]+)\]\[([\d.]+)s\].*?GC\(\d+\) Pause (Young|Full|Remark|Cleanup)([^\n]*?) (\d+)M->(\d+)M\((\d+)M\) ([\d.]+)ms', gc, re.M):
    up = float(m.group(2)); pauses.append((up, float(m.group(8)) / 1000))
    if m.group(3) in ('Young', 'Full'):
        pg.append((up, int(m.group(6)), m.group(3)))
pauses.sort()
stw = 0.0
for i, (t0, _) in enumerate(pauses):
    stw = max(stw, sum(d for t, d in pauses[i:] if t < t0 + 60) / 60)
fulls = [x for x in pg if x[2] == 'Full']
print('GC: pauses %d, full GCs %d, peak post-GC %d MiB, peak post-Full %s MiB, max STW share in a 60 s window %.0f %%' % (
    len(pauses), len(fulls), max((x[1] for x in pg), default=-1), max((x[1] for x in fulls), default='-'), 100 * stw))
sl = rd('system.log*'); dl = rd('debug.log*')
for pat in (r'Submitting index build of \[?v_idx[^\n]*', r'Starting a compaction index build[^\n]*', r'Index \[v_idx\] became queryable[^\n]*',
            r'Index build of \[?v_idx[^\n]*', r'Stopping active compactions[^\n]*'):
    for m in re.finditer(pat, sl + '\n' + dl):
        print('log:', m.group(0)[:300])
fl = re.findall(r'Global limit of .*? exceeded\. Current builder usage is ([\d.]+ ?\w+) for (\d+) cells', dl)
print('limiter flush lines: %d %s' % (len(fl), fl[:6]))
fin = re.findall(r'Flushing final segment for SSTable ([^ ]+) released (\d+)', dl)
print('final segment flushes: %d %s' % (len(fin), [(s[-40:], int(b) // MiB) for s, b in fin][:12]))
so = rd('stdout.txt')
m = re.search(r'java\.lang\.OutOfMemoryError[^\n]*', so)
print('stdout OOM:', m.group(0) if m else 'none', '|', ' | '.join(re.findall(r'(Dumping heap to [^\n]*|Heap dump file created[^\n]*)', so)))
ops = []
for l in open(os.path.join(R, 'stress.log'), errors='replace') if os.path.exists(os.path.join(R, 'stress.log')) else []:
    p = [x.strip() for x in l.split(',')]
    if len(p) > 3 and p[0] == 'total' and p[1].isdigit():
        try: ops.append(float(p[2]))
        except ValueError: pass
print('stress: %d intervals, mean %.0f op/s' % (len(ops), sum(ops) / len(ops) if ops else 0))
