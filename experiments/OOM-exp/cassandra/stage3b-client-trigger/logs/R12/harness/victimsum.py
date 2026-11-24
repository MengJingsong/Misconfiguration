#!/usr/bin/env python3
"""victimsum.py <run dir>: the victim's view from victim.txt (epoch_ms conn op latency_ms status) and markers.txt.
Writes <run dir>/victim-persec.txt (one line per second relative to attack_start: t ok err p50 p99 max statuses)
and prints a phase table: before (victim_start..attack_start), during (attack_start..endpoint), after (endpoint..
after_window_end), node down until restart (after_window_end..restart_cql_up), after restart (restart_cql_up..end)."""
import os, sys
from collections import Counter, defaultdict
R = sys.argv[1]
mk = {}
for l in open(os.path.join(R, 'markers.txt')):
    a, b = l.split(); mk[a] = int(b)
rows = []
for l in open(os.path.join(R, 'victim.txt')):
    p = l.split()
    if len(p) >= 5: rows.append((int(p[0]), p[2], int(p[3]), p[4]))
L = mk['attack_start']
E = next(mk[k] for k in mk if k.startswith('endpoint'))
def pct(v, q):
    if not v: return '-'
    v = sorted(v); return str(v[min(len(v) - 1, int(q * len(v)))])
per = defaultdict(list)
for t, op, lat, st in rows: per[(t - L) // 1000].append((op, lat, st))
with open(os.path.join(R, 'victim-persec.txt'), 'w') as f:
    f.write('# t_rel_attack_s n ok err p50_ms p99_ms max_ms statuses (markers: %s)\n' % ' '.join('%s=%+.1f' % (k, (v - L) / 1000) for k, v in sorted(mk.items(), key=lambda x: x[1])))
    for s in sorted(per):
        v = per[s]; ok = [x for x in v if x[2] == 'ok']; lat = [x[1] for x in ok]
        c = Counter(x[2] for x in v if x[2] != 'ok')
        f.write('%d %d %d %d %s %s %s %s\n' % (s, len(v), len(ok), len(v) - len(ok), pct(lat, .5), pct(lat, .99), max(lat) if lat else '-',
                ','.join('%s:%d' % kv for kv in c.most_common(3))))
ph = [('before', mk.get('victim_start'), L), ('during (attack..endpoint)', L, E), ('after (endpoint..+60 s)', E, mk.get('after_window_end')),
      ('node down to restart CQL up', mk.get('after_window_end'), mk.get('restart_cql_up')), ('after restart (CQL up..daemon stopped)', mk.get('restart_cql_up'), mk.get('restart_window_end'))]
print('phase | from..to (s rel. attack) | requests | ok %% | ok r / w | p50 | p99 | max | errors')
for name, a, b in ph:
    if a is None or b is None: continue
    v = [r for r in rows if a <= r[0] < b]
    ok = [r for r in v if r[3] == 'ok']; lat = [r[2] for r in ok]
    okr = sum(1 for r in ok if r[1] == 'r'); okw = len(ok) - okr; nr = sum(1 for r in v if r[1] == 'r'); nw = len(v) - nr
    c = Counter(r[3] for r in v if r[3] != 'ok')
    print('%s | %+.1f..%+.1f | %d | %.1f | %d/%d , %d/%d | %s | %s | %s | %s' % (name, (a - L) / 1000, (b - L) / 1000, len(v), 100.0 * len(ok) / max(1, len(v)),
          okr, nr, okw, nw, pct(lat, .5), pct(lat, .99), max(lat) if lat else '-', ', '.join('%s x%d' % kv for kv in c.most_common(4))))
okt = [r[0] for r in rows if r[3] == 'ok']
lastok = max([t for t in okt if t < E + 1000] or [0]); firstfail = min([r[0] for r in rows if r[0] >= L and r[3] != 'ok'] or [0])
back = min([t for t in okt if t > E + 5000] or [0])
print('last victim ok before the outage: %+.1f s; first victim error after attack start: %+.1f s; first ok after the outage: %+.1f s (restart_start %+.1f, restart_cql_up %+.1f); outage %.1f s' % (
      (lastok - L) / 1000, (firstfail - L) / 1000, (back - L) / 1000, (mk.get('restart_start', L) - L) / 1000, (mk.get('restart_cql_up', L) - L) / 1000, (back - lastok) / 1000))
