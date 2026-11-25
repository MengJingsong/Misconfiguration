#!/usr/bin/env python3
# B12 3-b confirm (from B19 3-b's vsum.py): the tenant's view per window from <run>/victim.out (B12Victim per-second
# lines), victim.start, attack.start, death.ms, and the attacker's per-second log attack/client.txt.
# Windows: before = victim start + 5 s .. attack start; attack = attack start .. JVM gone (split in 30-s slices);
# after = JVM gone .. tenant stop.   vsum.py <rundir>
import sys, os, statistics
d = sys.argv[1]; rd = lambda f: int(open(os.path.join(d, f)).read().split()[0])
vs, at = rd('victim.start'), rd('attack.start'); dead = rd('death.ms') if os.path.exists(os.path.join(d, 'death.ms')) else None
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
          f'ok/s median {statistics.median(r[2] for r in w)}, min {min(r[2] for r in w)}, p50 median {statistics.median(p50) if p50 else "-"} ms, '
          f'p99 max {max(p99) if p99 else "-"} ms, max {max(mx) if mx else "-"} ms, max inflight {max(r[8] for r in w)}; '
          f'last error: {next((r[12] for r in reversed(w) if r[12]), "")[:120]}')
print(f'victim.start {vs}  attack.start {at}  JVM gone {dead} (+{(dead-at)/1000 if dead else "NA"} s after attack start)')
win('before', vs + 5000, at)
end = dead or rows[-1][0]
t = at
while t < end:
    win(f'attack +{(t-at)//1000}..+{(min(t+30000,end)-at)//1000} s', t, min(t + 30000, end)); t += 30000
first_bad = next((r[0] for r in rows if r[0] > at and (r[2] < r[1] * 0.9 or r[10] > 1000)), None)
print(f'first tenant second with ok < 90 % of sent or p99 > 1 s: {first_bad} (+{(first_bad-at)/1000 if first_bad else "NA"} s after attack start)')
first_zero = next((r[0] for r in rows if r[0] > at and r[2] == 0), None)
print(f'first tenant second with 0 ok: {first_zero} (+{(first_zero-at)/1000 if first_zero else "NA"} s after attack start)')
if dead: win('after (JVM gone .. tenant stop)', dead, rows[-1][0] + 1)
# attacker progress
try:
    al = [l.split() for l in open(os.path.join(d, 'attack', 'client.txt')) if l[0].isdigit()]
    if al:
        last = al[-1]; print(f'attacker: last sample t={int(last[0])/1000:.1f} s issued={last[1]} ok={last[2]} err={last[3]}; '
                            f'ok at +60 s {next((x[2] for x in al if int(x[0]) >= 60000), "-")}, +120 s {next((x[2] for x in al if int(x[0]) >= 120000), "-")}')
except FileNotFoundError:
    pass
