#!/usr/bin/env python3
# R19: one §3 table row per arm from /mydata/r19-evidence/runs/<arm>/ (on pc96; from R11 table.py, design §2.5).
#   table.py <arm> [<arm> ...]
# Columns: arm | type | r | N | V outcome (+ inflow flags) | time to STOP, achieved rate | sent / ok / err | max pending
# (200 ms) | self-drops / hints | pre-burst live MiB | K key / counter | PSMW / KeyCacheKey / CounterCacheKey (pre) |
# h_stop | max after any GC / after Full GC (n Full) | worst-60 s STW | OOM mark after send / after STOP |
# max memtable on-heap MiB | R1 / R2 max pending, max after any GC % | dump Mutation / StorageProxy$4 / PSMW
import re, sys, glob
E = '/mydata/r19-evidence/runs/'
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
def f(x, fmt='{:,}'):
    return '—' if x is None else fmt.format(x)
for a in sys.argv[1:]:
    d = E + a + '/'; arm = rd(d + 'arm.log'); vd = d + 'V/'; o = rd(vd + 'outcome.txt'); obs = rd(d + 'obs-result').strip()
    hs = rd(d + 'hstop.txt').strip()
    ty = re.search(r'type=(\w)', arm); nn = re.search(r' N=(\d+)', arm); N = int(nn.group(1)) if nn else 0
    rt = re.search(r' rate=(\S+)', arm); rate = rt.group(1) if rt else '?'
    cl = rd(d + 'client/load.log'); fs = re.search(r'FIRST_SEND epochMs=(\d+)', cl)
    tr = re.search(r'^TOTAL_REACHED t=(\d+) sent=(\d+)', cl, re.M)
    fin = re.search(r'FINAL sent=(\d+) ok=(\d+) err=(\d+)', cl)
    mko = re.search(r'oom_mark_after_send=(\S+) oom_mark_after_stop=(\S+)', hs)
    oom = (mko and mko.group(1) != '-') or bool(rd(vd + 'dump.ls')) or (re.search(r'(\d+) OOMError lines', o) and int(re.search(r'(\d+) OOMError lines', o).group(1)) > 0)
    flags = []
    if 'RINGFAIL' in rd(d + 'outcome.txt') or 'FILLFAIL' in rd(d + 'outcome.txt'): out = 'void'
    elif 'V_ALIVE' in arm:
        sent = int(fin.group(1)) if fin else 0
        if N > 0 and sent < 0.98 * N: out = 'LOADSHORT (void)'
        elif obs == 'DRAINED': out = 'survive (drained)'
        elif obs == 'UNRESOLVED': out = 'unresolved'
        else: out = 'survive (window end, pending ≤ 1,000)'
    elif oom: out = '**heap OOM**' + (' (before STOP)' if 'censored' in hs else '')
    else: out = 'dead, no OOM evidence (void)'
    if tr and rate not in ('?', 'uncapped') and N > 0 and int(tr.group(1)) / 1000 > 1.25 * N / float(rate): flags.append('slow inflow')
    stop = f'{int(tr.group(1)) / 1000:.1f} s, {int(tr.group(2)) / (int(tr.group(1)) / 1000):,.0f}/s' if tr and int(tr.group(1)) > 0 else '—'
    okerr = f'{int(fin.group(1)):,} / {int(fin.group(2)):,} / {int(fin.group(3)):,}' if fin else '—'
    gl = rd(vd + 'gate.log'); mp = mx(r'(?m)^\d+ pending=(\d+)$', gl)
    hp = rd(vd + 'hist-pre.txt'); tot = re.search(r'^Total\s+(\d+)\s+(\d+)', hp, re.M)
    live = f'{int(tot.group(2)) / 2**20:.0f}' if tot else '—'
    psmw = hcount(hp, r'caffeine\.cache\.P'); kck = hcount(hp, r'\.KeyCacheKey$'); cck = hcount(hp, r'\.CounterCacheKey$')
    pre = arm.split('== pre-burst nodetool info')[-1] if '== pre-burst' in arm else ''
    kk = re.search(r'Key Cache\s*:.*?size ([\d.]+ \w+)', pre); ck = re.search(r'Counter Cache\s*:.*?size ([\d.]+ \w+)', pre)
    pl = rd(vd + 'poll.log')
    sd = mx(r'self_dropped=(\d+)', pl); hc = mx(r'hints_created=(\d+)', pl); mo = mx(r'memtable_onheap=(\d+)', pl)
    h_stop = re.search(r'h_stop=(\S+)', hs); ma = re.search(r'max_after_any=(\S+)', hs); mf = re.search(r'max_after_full=(\S+) n_full=(\d+)', hs)
    w60 = re.search(r'max60=(\d+)%', o)
    reps = []
    for r in ('R1', 'R2'):
        rp = mx(r'mut_pending=(\d+)', rd(d + r + '/poll.log')); ro = re.search(r'max_after_any=\d+MiB\(([\d.]+)%\)', rd(d + r + '/outcome.txt'))
        reps.append(f'{f(rp)}, {ro.group(1) if ro else "—"} %')
    dh = rd(vd + 'dump-hist.txt'); mu = re.search(r'(\d+) org\.apache\.cassandra\.db\.Mutation$', dh, re.M)
    sp = re.search(r'(\d+) org\.apache\.cassandra\.service\.StorageProxy\$4$', dh, re.M); dps = sum(int(x) for x in re.findall(r'(?m)^\s*[\d.]+ MiB\s+(\d+) com\.github\.benmanes\.caffeine\.cache\.P\S*$', dh)) if dh else None
    print(f'| `{a}` | {ty.group(1) if ty else "?"} | {rate} | {N:,} | {out}{(" · " + ", ".join(flags)) if flags else ""} | {stop} | {okerr} | {f(mp)} | '
          f'{f(sd)} / {f(hc)} | {live} | {kk.group(1) if kk else "—"} / {ck.group(1) if ck else "—"} | {psmw:,} / {kck:,} / {cck:,} | '
          f'{h_stop.group(1) if h_stop else "—"} | {ma.group(1) if ma else "—"} / {(mf.group(1) + " (" + mf.group(2) + ")") if mf else "—"} | '
          f'{(w60.group(1) + " %") if w60 else "—"} | {(mko.group(1) + " / " + mko.group(2)) if mko else "—"} | {f(mo and mo // 2**20)} | '
          f'{reps[0]}; {reps[1]} | {(mu.group(1) if mu else "—") + " / " + (sp.group(1) if sp else "—") + " / " + f(dps) if dh else "—"} |')
