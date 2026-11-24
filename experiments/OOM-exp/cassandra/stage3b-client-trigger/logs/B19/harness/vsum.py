#!/usr/bin/env python3
# B19 3-b confirm: the tenant's view per window from <run>/victim.out (B19Victim per-second lines), victim.start,
# attack.start, client.log (frame-sent ms = BOGUS ms - dt), death.ms.  Windows: before = victim start + 5 s .. attack
# start; attack = attack start .. JVM gone; after = JVM gone .. tenant stop.   vsum.py <rundir>
import sys, os, statistics
d = sys.argv[1]; rd = lambda f: int(open(os.path.join(d, f)).read().split()[0])
vs, at = rd('victim.start'), rd('attack.start'); dead = rd('death.ms') if os.path.exists(os.path.join(d, 'death.ms')) else None
frame = None
for l in open(os.path.join(d, 'client.log')):
    if l.startswith('BOGUS'):
        kv = dict(x.split('=') for x in l.split()[1:4]); frame = int(kv['ms']) - int(kv['dt'])
rows = []
for l in open(os.path.join(d, 'victim.out')):
    if not l.startswith('V 1'): continue
    f = l[2:].rstrip('\n').split(',', 12); rows.append([int(x) for x in f[:12]] + [f[12] if len(f) > 12 else ''])
def win(name, a, b):
    w = [r for r in rows if a < r[0] <= b]
    if not w: print(f'{name}: no seconds'); return
    sent = sum(r[1] for r in w); ok = sum(r[2] for r in w); err = [sum(r[i] for r in w) for i in (3, 4, 5, 6)]
    p50 = [r[9] for r in w if r[9] >= 0]; p99 = [r[10] for r in w if r[10] >= 0]; mx = [r[11] for r in w if r[11] >= 0]
    print(f'{name}: {len(w)} s, sent {sent}, ok {ok} ({100*ok/max(1,sent):.1f} %), errors timeout/unavail/nohost/other {err}, '
          f'ok/s median {statistics.median(r[2] for r in w)}, p50 median {statistics.median(p50) if p50 else "-"} ms, '
          f'p99 max {max(p99) if p99 else "-"} ms, max {max(mx) if mx else "-"} ms; last error: {next((r[12] for r in reversed(w) if r[12]), "")[:120]}')
print(f'victim.start {vs}  attack.start {at}  frame sent {frame} (+{frame-at} ms)  JVM gone {dead} (+{dead-at if dead else "NA"} ms after attack start, +{dead-frame if dead and frame else "NA"} ms after the frame)')
win('before', vs + 5000, at)
win('attack (start .. JVM gone)', at, dead or rows[-1][0])
first_zero = next((r[0] for r in rows if r[0] > at and r[2] == 0), None)
print(f'first tenant second with 0 ok: {first_zero} (+{first_zero-frame if first_zero and frame else "NA"} ms after the frame)')
if dead: win('after (JVM gone .. tenant stop)', dead, rows[-1][0] + 1)
