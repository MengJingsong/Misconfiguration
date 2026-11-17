#!/usr/bin/env python3
# S2 run 2: one table row per arm from the copied-back evidence (pc96).  table.py <arm> [<arm> ...]
# Columns: V outcome | OOM marker s after load start | max post-Full-GC MiB (%) | worst-60 s STW | longest >=90% window
# | V max MutationStage pending | dump Mutation / StorageProxy$4 | client ok / err | peak 5 s rate | replicas max post-Full-GC / max pending
import re, sys, glob, datetime
E = '/mydata/s2r2-evidence/runs/'
def rd(p):
    try: return open(p, errors='replace').read()
    except Exception: return ''
for a in sys.argv[1:]:
    d = E + a; arm = rd(d + '/arm.log'); o = rd(d + '/V/outcome.txt')
    alive = 'alive' if 'V_ALIVE' in arm else ('**OOM**' if 'ReportJavaOutOfMemory=1' in o or 'HeapDumper' in o else 'dead')
    # JVM uptime origin from the first GC log line
    g0 = None
    for f in sorted(glob.glob(d + '/V/gc.log*')):
        m = re.search(r'\[(\d{4}-\d\d-\d\dT[\d:.]+)([-+]\d{4})\]\[([\d.]+)s\]', rd(f))
        if m:
            t = datetime.datetime.strptime(m.group(1) + m.group(2), '%Y-%m-%dT%H:%M:%S.%f%z'); g0 = t.timestamp() - float(m.group(3)); break
    cl = rd(d + '/client/load.log'); m = re.search(r'\[(\d\d:\d\d:\d\d)\] t=(\d+)s', cl)
    ls = None
    if m and g0:
        day = datetime.datetime.fromtimestamp(g0, datetime.timezone(datetime.timedelta(hours=-7))).date()
        t = datetime.datetime.strptime(f'{day} {m.group(1)} -0700', '%Y-%m-%d %H:%M:%S %z').timestamp() - int(m.group(2)); ls = t - g0
    hd = re.search(r'HeapDumper@([\d.]+)s', o); oomt = f'{float(hd.group(1)) - ls:.0f}' if hd and ls is not None else '—'
    mf = re.search(r'max_after_full=(\d+)MiB\(([\d.]+)%\)', o); w60 = re.search(r'max60=(\d+)%', o); lw = re.search(r'longest>=90%win=(\d+)s', o)
    vnf = re.search(r'full_gcs=(\d+)', o).group(1); vma = re.search(r'max_after_any=(\d+)MiB\(([\d.]+)%\)', o)
    vlive = f'{mf.group(1)} ({mf.group(2)} %)' if vnf != '0' else f'no Full GC (≤ {vma.group(1)} ({vma.group(2)} %) after any GC)'
    sl = 'yes' if 'service_loss(all STW)=MET' in o else 'no'
    pend = max([int(x) for x in re.findall(r'mut_pending=(\d+)', rd(d + '/V/poll.log'))] or [0])
    dh = rd(d + '/V/dump-hist.txt'); mu = re.search(r'^org.apache.cassandra.db.Mutation: (\d+)', dh, re.M); sp = re.search(r'(\d+) org.apache.cassandra.service.StorageProxy\$4$', dh, re.M)
    fin = re.search(r'FINAL sent=(\d+) ok=(\d+) err=(\d+)', cl); rates = [int(x) for x in re.findall(r'\((\d+)/s\)', cl)]
    rs = []
    for n in ('R1', 'R2'):
        ro = rd(f'{d}/{n}/outcome.txt')
        if not ro: continue
        rm = re.search(r'max_after_full=(\d+)MiB\(([\d.]+)%\).*?ReportJavaOutOfMemory=(\d)', ro); rp = max([int(x) for x in re.findall(r'mut_pending=(\d+)', rd(f'{d}/{n}/poll.log'))] or [0])
        nf = re.search(r'full_gcs=(\d+)', ro).group(1); ma = re.search(r'max_after_any=\d+MiB\(([\d.]+)%\)', ro).group(1)
        rs.append(f'{n} ' + (f'{rm.group(2)} %' if nf != '0' else f'no Full GC (≤ {ma} % after any GC)') + f' / {rp}' + (' OOM' if rm.group(3) == '1' else ''))
    print(f'| `{a}` | {alive} | {oomt} | {vlive} | {w60.group(1)} % | {lw.group(1)} s ({sl}) | {pend} | '
          f'{(mu.group(1) + " / " + sp.group(1)) if mu and sp else "—"} | {int(fin.group(2)):,} / {int(fin.group(3)):,} | {max(rates or [0]):,} | {"; ".join(rs)} |')
