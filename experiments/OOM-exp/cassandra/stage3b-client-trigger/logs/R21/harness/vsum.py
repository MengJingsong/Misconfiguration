#!/usr/bin/env python3
# R21 3-b confirm (2026-11-23): the victim tenant's view per window (from B21's vsum.py), from <logs>/victim.out (R21Victim
# per-second lines), attack.start / attack.end (epoch ms, written by run3b.py; attack.end = node gone or attack client stopped).
#   before = victim start + 5 s .. attack start; during = attack start .. attack end; after = attack end .. victim stop.
#   vsum.py <logs/LABEL>
import sys, statistics
d = sys.argv[1]
V = []
for line in open(d + '/victim.out'):
    if line.startswith('V ') and line[2:3].isdigit():
        f = line[2:].rstrip('\n').split(',', 12)
        V.append([int(x) for x in f[:12]] + [f[12] if len(f) > 12 else ''])
a0 = int(open(d + '/attack.start').read()); a1 = int(open(d + '/attack.end').read())
if not V: print('no victim lines'); sys.exit()
v0 = V[0][0]
print(f"attack.start={a0} attack.end={a1} (attack {(a1 - a0) / 1000:.1f} s); victim {len(V)} s")
for name, t0, t1 in [('before', v0 + 5000, a0), ('during attack', a0, a1), ('after', a1, V[-1][0] + 1)]:
    w = [x for x in V if t0 < x[0] <= t1]
    if not w: print(f"  {name}: no seconds"); continue
    sent = sum(x[1] for x in w); ok = sum(x[2] for x in w); to = sum(x[3] for x in w); un = sum(x[4] for x in w)
    nh = sum(x[5] for x in w); ot = sum(x[6] for x in w); sk = sum(x[7] for x in w)
    done = ok + to + un + nh + ot
    p50 = [x[9] for x in w if x[9] >= 0]; p99 = [x[10] for x in w if x[10] >= 0]; mx = [x[11] for x in w if x[11] >= 0]
    zero = sum(1 for x in w if x[2] == 0)
    print(f"  {name}: {len(w)} s, sent {sent} ({sent / len(w):.1f}/s), ok {ok} / timeout {to}, unavailable {un}, nohost {nh}, other {ot}; skipped {sk}; "
          f"success {100.0 * ok / done if done else float('nan'):.1f} % of completions, ok/s {ok / len(w):.1f}; seconds with 0 ok: {zero}; "
          f"p50 median {statistics.median(p50) if p50 else 'NA'} ms, p99 max {max(p99) if p99 else 'NA'} ms, max {max(mx) if mx else 'NA'} ms; inflight max {max(x[8] for x in w)}")
    errs = [x[12] for x in w if x[12]]
    for e in list(dict.fromkeys(errs))[:3]: print(f"      err: {e}")
for x in V:
    if x[0] > a0 and (x[3] + x[4] + x[5] + x[6] > 0 or x[11] > 1000):
        print(f"first degraded victim second: +{(x[0] - a0) / 1000:.1f} s after attack start (ok {x[2]}, errs {x[3]}/{x[4]}/{x[5]}/{x[6]}, max {x[11]} ms)"); break
print("per second around the attack (t rel. attack start s: sent ok to un nh oth inflight p50 p99 max):")
for x in V:
    if a0 - 5000 <= x[0] <= a1 + 8000:
        print(f"  {(x[0] - a0) / 1000:+6.1f}: {x[1]} {x[2]} {x[3]} {x[4]} {x[5]} {x[6]} {x[8]} {x[9]} {x[10]} {x[11]} {x[12][:80]}")
