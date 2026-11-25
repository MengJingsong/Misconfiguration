#!/usr/bin/env python3
"""B13 3-b confirm: victim-tenant view per window. vsum.py <armdir> -> vsum.txt (also printed).
Windows: before the attack (victim start .. attack.start), attack until the first OOM line (system.log timestamp, UTC),
first OOM until the process was seen gone, after the death. Without OOM: before / attack (to the window end)."""
import csv, os, re, sys, datetime
R = sys.argv[1]
args = open(os.path.join(R, 'args.txt')).read()
def ev(pat):
    m = re.search(r'(\d{13}) ' + pat, args); return int(m.group(1)) if m else None
ta = ev(r'attack\.start'); dead = ev(r'V process gone'); oomseen = ev(r'OOM line seen')
toom = None
fo = os.path.join(R, 'first-oom.txt')
if os.path.exists(fo):
    for line in open(fo, errors='replace'):
        if re.search(r'OutOfMemoryError:|OutOfDirectMemoryError', line):
            break
    txt = open(fo, errors='replace').read()
    # timestamp of the line that carries the first OOM (or the closest preceding log line)
    ts = None
    for line in txt.splitlines():
        m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3})', line)
        if m:
            ts = m
        if re.search(r'OutOfMemoryError:|OutOfDirectMemoryError', line) and ts:
            break
    if ts:
        toom = int(datetime.datetime.strptime(ts.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) + int(ts.group(2))
rows = []
with open(os.path.join(R, 'victim.csv')) as f:
    for r in csv.DictReader(f):
        try:
            rows.append((int(r['t_ms']), int(r['attempted']), int(r['ok']), int(r['err']), float(r['p50ms']), float(r['p99ms']), float(r['maxms']), r['lastErr']))
        except (ValueError, KeyError, TypeError):
            pass
out = []
out.append(f'attack.start {ta}; first OOM (system.log) {toom} = +{(toom - ta) / 1000 if toom and ta else None} s; '
           f'OOM seen by harness {oomseen}; process gone {dead} = +{(dead - ta) / 1000 if dead and ta else None} s')
bounds = [('before attack', 0, ta)]
if toom:
    bounds += [('attack -> first OOM', ta, toom), ('first OOM -> process gone', toom, dead or 10**14), ('after death', dead or 10**14, 10**14)]
else:
    bounds += [('attack (no OOM)', ta, 10**14)]
for name, a, b in bounds:
    sel = [r for r in rows if a <= r[0] - 1000 < b]   # the line at t covers the second (t-1000, t]
    if not sel:
        out.append(f'{name}: no samples'); continue
    att = sum(r[1] for r in sel); ok = sum(r[2] for r in sel); er = sum(r[3] for r in sel)
    p50 = [r[4] for r in sel if r[4] >= 0]; p99 = [r[5] for r in sel if r[5] >= 0]; mx = [r[6] for r in sel if r[6] >= 0]
    errs = {}
    for r in sel:
        if r[7]:
            k = r[7].split(' ')[0]; errs[k] = errs.get(k, 0) + 1
    out.append(f'{name}: {len(sel)} s, attempted {att}, ok {ok} ({100.0 * ok / att if att else 0:.1f} %), err {er}; '
               f'per-second p50 {min(p50) if p50 else "-"}..{max(p50) if p50 else "-"} ms, p99 max {max(p99) if p99 else "-"} ms, '
               f'max {max(mx) if mx else "-"} ms; error kinds (seconds) {errs}')
# per-second detail around the attack
if ta:
    out.append('per second from attack.start (t_rel_s attempted ok err p50 p99 max lastErr):')
    for r in rows:
        if r[0] - 1000 >= ta - 2000:
            out.append(f'  {(r[0] - ta) / 1000:7.1f} {r[1]:3d} {r[2]:3d} {r[3]:3d} {r[4]:8.1f} {r[5]:8.1f} {r[6]:8.1f} {r[7]}')
txt = '\n'.join(out)
open(os.path.join(R, 'vsum.txt'), 'w').write(txt + '\n')
print('\n'.join(out[:len(bounds) + 1]))
