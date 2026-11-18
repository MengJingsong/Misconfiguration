#!/usr/bin/env python3
# G1 unified-log summary for one gc.log: pause count/total, Full GC count, max heap after any Full GC
# (live), max after any GC, fraction of wall time in pauses over the whole log and the worst 60 s window
# (service-loss criterion: >= 90 % over >= 60 s).
import re, sys
pat = re.compile(r'\]\[(\d+\.\d+)s\].*GC\((\d+)\) Pause (\S+).*?(\d+)M->(\d+)M\((\d+)M\) (\d+\.\d+)ms')
ev = []
for line in open(sys.argv[1], errors='replace'):
    m = pat.search(line)
    if m: ev.append((float(m[1]), m[3], int(m[4]), int(m[5]), int(m[6]), float(m[7]) / 1000))
if not ev: print('no pauses'); sys.exit()
full = [e for e in ev if e[1] == 'Full']
tot = sum(e[5] for e in ev); span = ev[-1][0] - ev[0][0] + ev[-1][5]
worst = 0.0; wstart = None
for i, e in enumerate(ev):
    s = 0.0
    for f in ev[i:]:
        if f[0] - e[0] > 60: break
        s += f[5]
    if s / 60 > worst: worst, wstart = s / 60, e[0]
cap = ev[-1][4]
print(f'pauses={len(ev)} full={len(full)} pause_total={tot:.1f}s span={span:.0f}s ({100*tot/max(span,1e-9):.0f}%) '
      f'worst60s={100*worst:.0f}% at {wstart}s; max_after_full={max([e[3] for e in full], default=0)}M '
      f'max_after_any={max(e[3] for e in ev)}M cap={cap}M last_at={ev[-1][0]:.0f}s')
