#!/usr/bin/env python3
"""3-b confirm B20: victim view per phase. victsum.py <run dir>  (reads victim.csv and phases.txt)
Per phase: seconds, sent, ok, success %, errors by type, median of per-second p50, max per-second p99, max latency,
and the longest run of seconds with 0 successes."""
import os, sys
rd = sys.argv[1]
ph = [l.split(None, 1) for l in open(os.path.join(rd, 'phases.txt')) if l.strip()]
ph = [(float(t), n.strip()) for t, n in ph]
rows = []
for l in open(os.path.join(rd, 'victim.csv')):
    if l.startswith('epoch'): continue
    p = l.rstrip('\n').split(',', 8)
    rows.append((int(p[0]), int(p[1]), int(p[2]), int(p[3]), int(p[4]), float(p[5]) if p[5] else None,
                 float(p[6]) if p[6] else None, float(p[7]) if p[7] else None, p[8]))
t0 = ph[0][0]
print(f'{"phase":<22}{"t0(s)":>8}{"secs":>6}{"sent":>7}{"ok":>7}{"ok%":>7}{"p50med":>8}{"p99max":>9}{"maxms":>9}{"zero-ok run":>12}  errors')
for i, (ts, name) in enumerate(ph):
    te = ph[i + 1][0] if i + 1 < len(ph) else float('inf')
    R = [r for r in rows if ts <= r[0] < te]
    if not R: print(f'{name:<22}{ts - t0:8.0f}     0'); continue
    sent = sum(r[1] for r in R); ok = sum(r[2] for r in R)
    p50 = sorted(r[5] for r in R if r[5] is not None); p99 = [r[6] for r in R if r[6] is not None]
    mx = [r[7] for r in R if r[7] is not None]
    et = {}
    for r in R:
        for kv in filter(None, r[8].split(';')):
            k, c = kv.rsplit(':', 1); et[k] = et.get(k, 0) + int(c)
    run = best = 0
    for r in R:
        run = run + 1 if r[2] == 0 else 0; best = max(best, run)
    print(f'{name:<22}{ts - t0:8.0f}{len(R):6d}{sent:7d}{ok:7d}{100 * ok / sent if sent else 0:7.1f}'
          f'{p50[len(p50) // 2] if p50 else float("nan"):8.2f}{max(p99) if p99 else float("nan"):9.1f}'
          f'{max(mx) if mx else float("nan"):9.1f}{best:12d}  {et if et else ""}')
