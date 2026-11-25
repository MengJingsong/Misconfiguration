#!/usr/bin/env python3
# R25 (2026-11-24, case file §2.5): inflow smoothness of one arm from the client's load.log.
#   smooth.py <evidence run dir> <r writes/s> [slots, default 4096]
# Per full second (one progress line, rate normalised by the line's actual interval) between FIRST_SEND and the end
# point = min(STOP (TOTAL_REACHED), V's death (V/poll.log DEAD), t_sat = the first second with inflightMax >= 0.9 slots):
# sends, min / max / sd, fraction of seconds within +-10 % of r; achieved rate N / t_STOP.
# SMOOTH = every full second before the end point <= 1.10 r, >= 90 % of them >= 0.90 r, and (arm in which V survives)
# no saturation before STOP and N / t_STOP >= 0.95 r.  First line: SMOOTH | NOT_SMOOTH (<which>), then details, then the series.
import re, sys, statistics
d = sys.argv[1].rstrip('/') + '/'; r = float(sys.argv[2]); slots = int(sys.argv[3]) if len(sys.argv) > 3 else 4096
def rd(p):
    try: return open(p, errors='replace').read()
    except Exception: return ''
cl = rd(d + 'client/load.log'); arm = rd(d + 'arm.log')
fs = re.search(r'^FIRST_SEND epochMs=(\d+)', cl, re.M); tr = re.search(r'^TOTAL_REACHED t=(\d+) sent=(\d+) ok=\d+ epochMs=(\d+)', cl, re.M)
if not fs or int(fs.group(1)) == 0: print('NOT_SMOOTH (no FIRST_SEND)'); sys.exit()
t0 = int(fs.group(1)); stop = int(tr.group(3)) if tr else None
dead = None
m = re.search(r'^(\d+) DEAD', rd(d + 'V/poll.log'), re.M)
if m: dead = int(m.group(1)) * 1000
alive = 'V_ALIVE' in arm
L = [(int(a), int(b), int(c), int(e)) for a, b, c, e in re.findall(r'epochMs=(\d+) t=[\d.]+ sent=(\d+) .*?inflightMax=(\d+) late=(\d+)', cl)]
rows = []; prev = None; tsat = None
for ep, sn, im, lt in L:
    st = prev[0] if prev else ep - 1000; ps = prev[1] if prev else 0
    prev = (ep, sn)
    if st < t0 - 200: continue
    rate = (sn - ps) * 1000.0 / max(1, ep - st)
    rows.append((st, ep, rate, im, lt))
    if tsat is None and im >= 0.9 * slots: tsat = ep
ends = [x for x in (stop, dead, tsat) if x is not None]
endp = min(ends) if ends else (rows[-1][1] if rows else t0)
full = [x for x in rows if x[1] <= endp]
rates = [x[2] for x in full]
reasons = []
if not rates: reasons.append('no full second')
else:
    if max(rates) > 1.10 * r: reasons.append(f'max {max(rates):,.0f} > 1.10 r')
    lo = sum(1 for x in rates if x >= 0.90 * r) / len(rates)
    if lo < 0.90: reasons.append(f'only {100*lo:.0f} % of seconds >= 0.90 r')
ach = None
if tr and int(tr.group(1)) > 0: ach = int(tr.group(2)) / (int(tr.group(1)) / 1000)
if alive:
    if tsat is not None and (stop is None or tsat <= stop): reasons.append(f'saturated before STOP (t_sat {(tsat - t0)/1000:.0f} s)')
    if ach is None or ach < 0.95 * r: reasons.append(f'achieved {ach and round(ach):,} < 0.95 r' if ach else 'no STOP')
within = (sum(1 for x in rates if 0.9 * r <= x <= 1.1 * r) / len(rates)) if rates else 0
print('SMOOTH' if not reasons else 'NOT_SMOOTH (' + '; '.join(reasons) + ')')
print(f'r={r:.0f} n_full={len(rates)} min={min(rates, default=0):,.0f} max={max(rates, default=0):,.0f} '
      f'sd={statistics.pstdev(rates) if len(rates) > 1 else 0:,.0f} within10={100*within:.0f}% achieved={(f"{ach:,.0f}" if ach else "-")} '
      f't_stop={(stop - t0)/1000 if stop else "-"} t_sat={(f"{(tsat - t0)/1000:.0f}" if tsat else "-")} t_dead={(f"{(dead - t0)/1000:.0f}" if dead else "-")} '
      f'late_total={sum(x[4] for x in full)} inflightMax_max={max((x[3] for x in full), default=0)} V_alive={alive}')
for st, ep, rate, im, lt in rows:
    print(f'{(ep - t0)/1000:6.1f} s  sends/s={rate:7,.0f} inflightMax={im:5d} late={lt}{"  (after end point)" if ep > endp else ""}')
