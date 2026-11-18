#!/usr/bin/env python3
# R8: one §3 table row per arm from /mydata/s4/r8-w1/runs/<arm>/ (on pc91).   table.py <arm> [<arm> ...]
# Columns: arm | type | N | V outcome | OOM marker s after burst start | client ok/err (burst s) | pre-burst live heap MiB
# (forced-GC histogram) | key / counter K MiB pre-burst | Caffeine nodes / KeyCacheKey / CounterCacheKey (pre) |
# max mut_pending | max heap used MiB (1 s poll) | max after any GC MiB (%) | Full GCs / max after Full MiB | worst-60 s STW |
# dump Mutation / StorageProxy$4
import re, sys, glob, datetime
W = '/mydata/s4/r8-w1/runs/'
def rd(p):
    try: return open(p, errors='replace').read()
    except Exception: return ''
def hcount(h, pat):
    t = 0
    for m in re.finditer(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', h, re.M):
        if re.search(pat, m.group(3)): t += int(m.group(1))
    return t
for a in sys.argv[1:]:
    d = W + a + '/'; arm = rd(d + 'arm.log'); o = rd(d + 'outcome.txt')
    ty = re.search(r'type=(\w)', arm); n = re.search(r' N=(\d+)', arm)
    t0 = float(rd(d + 'T0').strip() or 0)
    marks = []
    for f in sorted(glob.glob(d + 'gc.log*')):
        for line in open(f, errors='replace'):
            if 'safepoint region: HeapDumper' in line or 'safepoint region: ReportJavaOutOfMemory' in line:
                m = re.match(r'\[(\d{4}-\d\d-\d\dT[\d:.]+)([-+]\d{4})\]', line)
                if m: marks.append(datetime.datetime.strptime(m.group(1) + m.group(2), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp())
    oom = bool(marks) or 'HeapDumper' in o or re.search(r'ReportJavaOutOfMemory=[1-9]', o) or bool(rd(d + 'dump.ls'))
    if 'RINGFAIL' in o or 'FILLFAIL' in o: out = 'void'
    elif 'V_ALIVE' in arm: out = 'survive'
    elif oom: out = '**heap OOM**'
    else: out = 'dead, no OOM evidence (void)'
    oomt = f'{min(marks) - t0:.0f}' if marks and t0 else '—'
    cl = rd(d + 'load.log'); fin = re.search(r'FINAL sent=(\d+) ok=(\d+) err=(\d+) firstOkMs=(\d+) lastOkMs=(\d+)', cl)
    burst = f'{(int(fin.group(5)) - int(fin.group(4))) / 1000:.0f}' if fin and int(fin.group(4)) else '—'
    okerr = f'{int(fin.group(2)):,} / {int(fin.group(3)):,} ({burst} s)' if fin else '—'
    hp = rd(d + 'hist-pre.txt'); tot = re.search(r'^Total\s+(\d+)\s+(\d+)', hp, re.M)
    live = f'{int(tot.group(2)) / 2**20:.0f}' if tot else '—'
    psmw = hcount(hp, r'caffeine\.cache\.P'); kck = hcount(hp, r'\.KeyCacheKey$'); cck = hcount(hp, r'\.CounterCacheKey$')
    pre = arm.split('== pre-burst nodetool info')[-1] if '== pre-burst' in arm else ''
    kk = re.search(r'Key Cache\s*:.*?size ([\d.]+ \w+)', pre); ck = re.search(r'Counter Cache\s*:.*?size ([\d.]+ \w+)', pre)
    pl = rd(d + 'poll.log')
    pend = max([int(x) for x in re.findall(r'mut_pending=(\d+)', pl)] or [0])
    hu = max([int(x) for x in re.findall(r'heapMiB=(\d+)/', pl)] or [0])
    ma = re.search(r'max_after_any=(\d+)MiB\(([\d.]+)%\)', o); nf = re.search(r'full_gcs=(\d+) max_after_full=(\d+)MiB', o)
    w60 = re.search(r'max60=(\d+)%', o)
    dh = rd(d + 'dump-hist.txt'); mu = re.search(r'(\d+) org\.apache\.cassandra\.db\.Mutation$', dh, re.M); sp = re.search(r'(\d+) org\.apache\.cassandra\.service\.StorageProxy\$4$', dh, re.M)
    print(f'| `{a}` | {ty.group(1) if ty else "?"} | {int(n.group(1)):,} | {out} | {oomt} | {okerr} | {live} | '
          f'{kk.group(1) if kk else "—"} / {ck.group(1) if ck else "—"} | {psmw:,} / {kck:,} / {cck:,} | {pend:,} | {hu:,} | '
          f'{(ma.group(1) + " (" + ma.group(2) + " %)") if ma else "—"} | {(nf.group(1) + " / " + nf.group(2)) if nf else "—"} | '
          f'{(w60.group(1) + " %") if w60 else "—"} | {(mu.group(1) + " / " + sp.group(1)) if mu and sp else "—"} |')
