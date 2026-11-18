#!/usr/bin/env python3
"""C8 self-check: re-parse one run directory (gauges.csv, gc.log*, debug.log*, system.log, launch.log, stress.log, hist-*.txt,
notes.txt, meta.txt) and print the outcome line (last line of output). usage: selfcheck.py <rundir> [-v]"""
import glob, io, os, re, sys, zipfile
from datetime import datetime

R = sys.argv[1]
V = '-v' in sys.argv
meta = dict(l.strip().split('=', 1) for l in open(R + '/meta.txt') if '=' in l)
notes = open(R + '/notes.txt').read() if os.path.exists(R + '/notes.txt') else ''
t_arm = int(open(R + '/t_arm.txt').read()) if os.path.exists(R + '/t_arm.txt') else None
MiB = 2 ** 20


def read_all(pattern):
    out = []
    for f in sorted(glob.glob(R + '/' + pattern)):
        if f.endswith('.zip'):
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    out.append(z.read(n).decode(errors='replace'))
        else:
            out.append(open(f, errors='replace').read())
    return '\n'.join(out)


# gauges
rows = []
if os.path.exists(R + '/gauges.csv'):
    for l in open(R + '/gauges.csv'):
        p = l.strip().split(',')
        if len(p) >= 11 and p[0].isdigit():
            rows.append([int(x) for x in p])
k1 = max((r[1] for r in rows), default=-1)
lim = sorted({r[2] for r in rows if r[2] > 0})
k2 = max((r[6] for r in rows), default=-1)
hu = max((r[4] for r in rows), default=-1)
blocked = max((r[7] for r in rows), default=-1)
kc = max((r[11] for r in rows if len(r) > 12), default=-1)
kce = max((r[12] for r in rows if len(r) > 12), default=-1)
# K_D2 at the time K_D1 is within 10 % of its peak
k2_at_k1 = max((r[6] for r in rows if k1 > 0 and r[1] >= 0.9 * k1), default=-1)
last_ms = rows[-1][0] if rows else None
# number of K_D1 peaks (drops > 30 % of limit)
cycles = 0
if rows and lim:
    up = False
    for r in rows:
        if r[1] >= 0.9 * lim[-1]:
            up = True
        elif up and r[1] < 0.5 * lim[-1]:
            cycles += 1; up = False
    if up:
        cycles += 1

# gc log
gc = read_all('gc.log*')
pg = []
pauses = []
for m in re.finditer(r'^\[([^\]]+)\]\[([\d.]+)s\].*?GC\(\d+\) Pause (Young|Full|Remark|Cleanup)([^\n]*?) (\d+)M->(\d+)M\((\d+)M\) ([\d.]+)ms', gc, re.M):
    up_s = float(m.group(2)); kind = m.group(3) + m.group(4)
    pauses.append((up_s, float(m.group(8)) / 1000))
    if m.group(3) in ('Young', 'Full'):
        pg.append((up_s, int(m.group(6)), kind))
peak_pg = max((x[1] for x in pg), default=-1)
peak_full = max((x[1] for x in pg if x[2].startswith('Full')), default=-1)
nfull = sum(1 for x in pg if x[2].startswith('Full'))
# service-loss: max STW fraction in a 60 s window
pauses.sort(); pg.sort()
stw = 0.0
if pauses:
    for i, (t0, _) in enumerate(pauses):
        s = sum(d for t, d in pauses[i:] if t < t0 + 60)
        stw = max(stw, s / 60)

# logs
sl = read_all('system.log*')
dl = read_all('debug.log*')
ll = read_all('launch.log')
flush = re.findall(r'Global limit of .*? exceeded\. Current builder usage is ([\d.]+ ?\w+) for (\d+) cells', dl)
oom = re.search(r'OutOfMemoryError: [^\n]*', ll + '\n' + sl)
kind = 'none'
died = 'node_died_before_stop=True' in notes
if oom:
    t = oom.group(0)
    kind = 'heap-OOM' if 'Java heap space' in t or 'GC overhead' in t else ('direct-OOM' if 'Direct buffer' in t else 'OOM:' + t[:60])
elif died:
    kind = 'died-no-OOM-line'
if 'node did not come up' in notes:
    kind = 'invalid(no-start)'
hprof = glob.glob(R + '/*.hprof')
# endpoint time: last gauge sample after arm start
t_end = f'{(last_ms - t_arm) / 1000:.0f}s' if (oom or died) and last_ms and t_arm else '-'

# stress
ops = []
if os.path.exists(R + '/stress.log'):
    for l in open(R + '/stress.log', errors='replace'):
        p = [x.strip() for x in l.split(',')]
        if len(p) > 3 and p[0] == 'total' and p[1].isdigit():
            try:
                ops.append(float(p[2]))
            except ValueError:
                pass
mean_ops = f'{sum(ops) / len(ops):.0f}' if ops else '-'


def histo(path):
    if not os.path.exists(path):
        return None
    t = open(path, errors='replace').read()
    tot = re.search(r'^Total\s+(\d+)\s+(\d+)', t, re.M)
    def c(cls):
        m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+' + re.escape(cls) + r'(\s|$)', t, re.M)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    return dict(total=int(tot.group(2)) if tot else -1, plv=c('org.apache.lucene.util.packed.DeltaPackedLongValues$Builder'), kck=c('org.apache.cassandra.cache.KeyCacheKey'),
                larr=c('[J'), region=c('org.apache.cassandra.utils.memory.SlabAllocator$Region'), barr=c('[B'))


h0 = histo(R + '/hist-B0.txt')
hp = histo(R + '/hist-peak.txt')
b0 = f'{h0["total"] / MiB:.0f}' if h0 else '-'
hps = (f'peakhist total {hp["total"] / MiB:.0f}MiB PLV$Builder {hp["plv"][0]} long[] {hp["larr"][1] / MiB:.0f}MiB '
       f'byte[] {hp["barr"][1] / MiB:.0f}MiB Region {hp["region"][0]} KeyCacheKey {hp["kck"][0]}') if hp else 'peakhist -'
bm = re.search(r'builds_completed=(\d+)', notes)
qm = re.search(r'query_check count=(\S+)', notes)
line = (f'{os.path.basename(R)} arm={meta["arm"]} H={meta["heap"]} sai={meta["sai"]} endpoint={kind} t_end={t_end} '
        f'peakK1={k1 / MiB:.0f}MiB limit={[x // MiB for x in lim]} K1cycles={cycles} peakK2={k2 / MiB:.0f}MiB K2@K1peak={k2_at_k1 / MiB:.0f}MiB '
        f'peakHeapUsed={hu / MiB:.0f}MiB peakPostGC={peak_pg}MiB peakPostFull={peak_full}MiB fullGCs={nfull} maxSTW60s={stw * 100:.0f}% B0={b0}MiB '
        f'builds={bm.group(1) if bm else "-"} query={qm.group(1) if qm else "-"} flushLines={len(flush)} '
        f'stressOps/s={mean_ops} blocked={blocked} peakKC={kc / MiB:.0f}MiB/{kce}e hprof={len(hprof)} {hps}')
if V:
    print('first OOM line:', oom.group(0) if oom else None)
    print('flush lines sample:', flush[:3])
print(line)
