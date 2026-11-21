#!/usr/bin/env python3
# R11: one §3 table row per arm from /mydata/r11-evidence/runs/<arm>/ (on pc96; from R8 table.py + gate columns).
#   table.py <arm> [<arm> ...]
# Columns: arm | type | G | V outcome | OOM mark s after first send / after gate | gate: s to STOP, sent at STOP |
# client FINAL ok / err | max pending (gate 200 ms) (overshoot over G) | pre-burst live MiB (forced-GC histogram) |
# K key / counter pre-burst | Caffeine nodes / KeyCacheKey / CounterCacheKey (pre) | self-dropped / hints_created /
# max hints_inprog (V) | max memtable on-heap MiB (V, b6) | max heap used MiB (1 s) | max after any GC MiB (%) |
# Full GCs / max after Full MiB | worst-60 s STW | R1 / R2 max pending, max after any GC % | dump Mutation / StorageProxy$4
import re, sys, glob, datetime
E = '/mydata/r11-evidence/runs/'
def rd(p):
    try: return open(p, errors='replace').read()
    except Exception: return ''
def hcount(h, pat):
    t = 0
    for m in re.finditer(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', h, re.M):
        if re.search(pat, m.group(3)): t += int(m.group(1))
    return t
def mx(pat, txt, cast=int):
    v = [cast(x) for x in re.findall(pat, txt)]
    return max(v) if v else None
def marks(d):
    ms = []
    for f in sorted(glob.glob(d + 'gc.log*')):
        for line in open(f, errors='replace'):
            if 'safepoint region: HeapDumper' in line or 'safepoint region: ReportJavaOutOfMemory' in line:
                m = re.match(r'\[(\d{4}-\d\d-\d\dT[\d:.]+)([-+]\d{4})\]', line)
                if m: ms.append(datetime.datetime.strptime(m.group(1) + m.group(2), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp())
    return ms
def f(x, fmt='{:,}'):
    return '—' if x is None else fmt.format(x)
for a in sys.argv[1:]:
    d = E + a + '/'; arm = rd(d + 'arm.log'); vd = d + 'V/'; o = rd(vd + 'outcome.txt'); obs = rd(d + 'obs-result').strip()
    ty = re.search(r'type=(\w)', arm); g = re.search(r' G=(\d+)', arm); G = int(g.group(1)) if g else 0
    cl = rd(d + 'client/load.log'); fs = re.search(r'FIRST_SEND epochMs=(\d+)', cl); t0 = int(fs.group(1)) / 1000 if fs else None
    gl = rd(vd + 'gate.log'); gt = re.search(r'^GATE t=(\d+) pending=(\d+)', gl, re.M)
    sr = re.search(r'STOP_RECEIVED t=(\d+) sent=(\d+)', cl)
    mk = marks(vd)
    oom = bool(mk) or bool(rd(vd + 'dump.ls')) or (re.search(r'(\d+) OOMError lines', o) and int(re.search(r'(\d+) OOMError lines', o).group(1)) > 0)
    if 'RINGFAIL' in rd(d + 'outcome.txt') or 'FILLFAIL' in rd(d + 'outcome.txt'): out = 'void'
    elif 'V_ALIVE' in arm:
        if G > 0 and not gt: out = 'LOADFAIL (void)'
        elif obs == 'DRAINED': out = 'survive (drained)'
        elif obs == 'UNRESOLVED': out = 'unresolved'
        else: out = 'survive (window end, pending ≤ 1,000)'
    elif oom: out = '**heap OOM**'
    else: out = 'dead, no OOM evidence (void)'
    oomt = (f'{min(mk) - t0:.0f} / ' + (f'{min(mk) - int(gt.group(1)) / 1000:.0f}' if gt else '—')) if mk and t0 else '—'
    gate = f'{int(sr.group(1)) / 1000:.1f} s, {int(sr.group(2)):,}' if sr else ('gate ' + gt.group(2) + ', no STOP at client' if gt else '—')
    fin = re.search(r'FINAL sent=(\d+) ok=(\d+) err=(\d+)', cl)
    okerr = f'{int(fin.group(2)):,} / {int(fin.group(3)):,}' if fin else '—'
    mp = mx(r'(?m)^\d+ pending=(\d+)$', gl)
    ov = f' (+{mp - G:,})' if mp is not None and G > 0 else ''
    hp = rd(vd + 'hist-pre.txt'); tot = re.search(r'^Total\s+(\d+)\s+(\d+)', hp, re.M)
    live = f'{int(tot.group(2)) / 2**20:.0f}' if tot else '—'
    psmw = hcount(hp, r'caffeine\.cache\.P'); kck = hcount(hp, r'\.KeyCacheKey$'); cck = hcount(hp, r'\.CounterCacheKey$')
    pre = arm.split('== pre-burst nodetool info')[-1] if '== pre-burst' in arm else ''
    kk = re.search(r'Key Cache\s*:.*?size ([\d.]+ \w+)', pre); ck = re.search(r'Counter Cache\s*:.*?size ([\d.]+ \w+)', pre)
    pl = rd(vd + 'poll.log')
    sd = mx(r'self_dropped=(\d+)', pl); hc = mx(r'hints_created=(\d+)', pl); hi = mx(r'hints_inprog=(\d+)', pl)
    mo = mx(r'memtable_onheap=(\d+)', pl); hu = mx(r'heapMiB=(\d+)/', pl)
    ma = re.search(r'max_after_any=(\d+)MiB\(([\d.]+)%\)', o); nf = re.search(r'full_gcs=(\d+) max_after_full=(\d+)MiB', o)
    w60 = re.search(r'max60=(\d+)%', o)
    reps = []
    for r in ('R1', 'R2'):
        rp = mx(r'mut_pending=(\d+)', rd(d + r + '/poll.log')); ro = re.search(r'max_after_any=\d+MiB\(([\d.]+)%\)', rd(d + r + '/outcome.txt'))
        reps.append(f'{f(rp)}, {ro.group(1) if ro else "—"} %')
    dh = rd(vd + 'dump-hist.txt'); mu = re.search(r'(\d+) org\.apache\.cassandra\.db\.Mutation$', dh, re.M); sp = re.search(r'(\d+) org\.apache\.cassandra\.service\.StorageProxy\$4$', dh, re.M)
    print(f'| `{a}` | {ty.group(1) if ty else "?"} | {G:,} | {out} | {oomt} | {gate} | {okerr} | {f(mp)}{ov} | {live} | '
          f'{kk.group(1) if kk else "—"} / {ck.group(1) if ck else "—"} | {psmw:,} / {kck:,} / {cck:,} | {f(sd)} / {f(hc)} / {f(hi)} | '
          f'{f(mo and mo // 2**20)} | {f(hu)} | {(ma.group(1) + " (" + ma.group(2) + " %)") if ma else "—"} | '
          f'{(nf.group(1) + " / " + nf.group(2)) if nf else "—"} | {(w60.group(1) + " %") if w60 else "—"} | {reps[0]}; {reps[1]} | '
          f'{(mu.group(1) + " / " + sp.group(1)) if mu and sp else "—"} |')
