#!/usr/bin/env python3
"""victim-summary.py <run dir>: the victim role's view of a U9 3-b confirm run. Reads victim.csv
(t_send_ms,op,outcome,latency_ms) and events.txt (<epoch ms> <event>). Phases are cut at the events, in time order:
before (victim start .. attack_start), during attack (.. oom_seen), down (oom_seen .. restart_ready), after restart
(restart_ready .. oom_seen_restart or victim stop), down again (oom_seen_restart ..). Writes victim-persec.csv (per
second relative to attack_start: ops, ok, err, skip, ok-latency p50/p99/max) and prints per-phase aggregates."""
import os, sys
from collections import defaultdict
R = sys.argv[1]
evs = {}
for l in open(os.path.join(R, 'events.txt')):
    t, name = l.split(None, 1)
    evs.setdefault(name.strip(), int(t))
ops = []
for l in open(os.path.join(R, 'victim.csv'), errors='replace'):
    if not l.strip() or l[0] == '#':
        continue
    t, op, out, lat = l.strip().split(',')
    ops.append((int(t), op, out, int(lat)))
ops.sort()
t_att = evs.get('attack_start')
print('events (s from attack_start): ' + ', '.join('%s %+.1f' % (k, (v - t_att) / 1000) for k, v in sorted(evs.items(), key=lambda x: x[1])))
if not ops:
    print('no victim ops'); sys.exit(0)
end = ops[-1][0] + 1
cuts = [('before', ops[0][0]), ('during attack', t_att)]
if 'oom_seen' in evs:
    cuts.append(('down (OOM -> restart ready)', evs['oom_seen']))
elif 'jvm_dead' in evs:
    cuts.append(('down (JVM dead -> restart ready)', evs['jvm_dead']))
if 'restart_ready' in evs:
    cuts.append(('after restart (up)', evs['restart_ready']))
if 'oom_seen_restart' in evs:
    cuts.append(('down again (2nd OOM ->)', evs['oom_seen_restart']))
cuts.append(('end', end))


def pct(v, p):
    if not v: return None
    v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))]


def agg(sel):
    n = len(sel); ok = [o for o in sel if o[2] == 'ok']; err = defaultdict(int)
    for o in sel:
        if o[2] != 'ok': err[o[2]] += 1
    lat = [o[3] for o in ok]
    return n, len(ok), dict(err), pct(lat, .5), pct(lat, .99), max(lat) if lat else None


for (name, a), (_, b) in zip(cuts, cuts[1:]):
    sel = [o for o in ops if a <= o[0] < b]
    n, ok, err, p50, p99, mx = agg(sel)
    print('%-34s %7.1f s  ops %6d  ok %6d (%5.1f %%)  err %s  ok-latency ms p50 %s p99 %s max %s' % (
        name, (b - a) / 1000, n, ok, 100.0 * ok / n if n else 0, err, p50, p99, mx))
bins = defaultdict(list)
for o in ops:
    bins[(o[0] - t_att) // 1000].append(o)
with open(os.path.join(R, 'victim-persec.csv'), 'w') as f:
    f.write('sec_from_attack_start,ops,ok,err,skip,p50_ms,p99_ms,max_ms\n')
    for s in sorted(bins):
        sel = bins[s]; n, ok, err, p50, p99, mx = agg(sel)
        sk = err.get('skip', 0)
        f.write('%d,%d,%d,%d,%d,%s,%s,%s\n' % (s, n, ok, n - ok - sk, sk, p50, p99, mx))
bad = [s for s in sorted(bins) if s >= 0 and sum(1 for o in bins[s] if o[2] == 'ok') < 0.5 * len(bins[s])]
print('first second (from attack_start) with victim ok < 50 %%: %s' % (bad[0] if bad else 'none'))
ok_after = [s for s in sorted(bins) if bad and s > bad[0] and all(o[2] == 'ok' for o in bins[s])]
print('first fully-ok second after that: %s' % (ok_after[0] if ok_after else 'none'))
slow = [s for s in sorted(bins) if 0 <= s and (agg(bins[s])[4] or 0) > 500]
print('seconds during/after the attack with victim ok-latency p99 > 500 ms: %d (first %s)' % (len(slow), slow[0] if slow else None))
