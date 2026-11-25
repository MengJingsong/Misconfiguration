#!/usr/bin/env python3
"""B9 3-b confirm: victim summary per window from <run>/victim.log and <run>/run.meta.
Windows: before = victim_start..attack_start; during = attack_start..node_exit (or attack_end if the node lived);
after = the rest until victim_end. Success = OK / all ticks (missed, down and connect failures count as failures).
Writes victim-sec.csv (per second: t_rel_s, ticks, ok, fail, p99_ok_ms, max_ms, last status)."""
import sys, os, collections

R = sys.argv[1]
meta = {}
for l in open(os.path.join(R, 'run.meta')):
    p = l.split()
    if len(p) == 2 and p[1].isdigit():
        meta.setdefault(p[0], int(p[1]))
a0 = meta['attack_start']
if meta.get('node_exit') and meta['node_exit'] >= meta.get('victim_end', 10 ** 15):
    del meta['node_exit']          # exit by ctl.sh stop after the victim ended: not a death
dend = meta.get('node_exit') or meta['attack_end']
ev = []
for l in open(os.path.join(R, 'victim.log')):
    if l.startswith('#'): continue
    p = l.split()
    if len(p) < 4: continue
    ev.append((int(p[0]), p[1], int(p[2]), p[3]))


def pct(xs, q):
    if not xs: return float('nan')
    xs = sorted(xs); return xs[min(len(xs) - 1, int(q * len(xs)))]


def win(name, t0, t1):
    e = [x for x in ev if t0 <= x[0] < t1]
    ok = [x for x in e if x[3] == 'OK']
    kinds = collections.Counter(('OK' if x[3] == 'OK' else x[3].split(':')[0] + (':' + x[3].split(':')[1] if x[3].startswith('ERR') else '')) for x in e)
    lat = [x[2] for x in ok]
    s = 100.0 * len(ok) / len(e) if e else float('nan')
    print('%-7s %6.1f s  ticks %5d  ok %5d  success %5.1f %%  ok-latency p50 %s p99 %s max %s ms  %s' % (
        name, (t1 - t0) / 1000, len(e), len(ok), s, pct(lat, .5), pct(lat, .99), max(lat) if lat else '-', dict(kinds)))
    return e


print('attack_start %d; during ends at %s (%s); times below relative to attack_start' % (a0, dend, 'node_exit' if meta.get('node_exit') else 'attack_end'))
win('before', meta['victim_start'], a0)
d = win('during', a0, dend)
win('after', dend, meta.get('victim_end', 10 ** 15))
fails = [x for x in ev if x[0] >= a0 and x[3] != 'OK']
oks = [x for x in ev if x[0] >= a0 and x[3] == 'OK']
if fails: print('first failure after attack start: +%.2f s (%s %s)' % ((fails[0][0] - a0) / 1000, fails[0][3], fails[0][2]))
if oks: print('last OK after attack start: +%.2f s' % ((oks[-1][0] - a0) / 1000))
if meta.get('node_exit'): print('node exit: +%.2f s after attack_start' % ((meta['node_exit'] - a0) / 1000))
sec = collections.defaultdict(list)
for x in ev: sec[(x[0] - a0) // 1000].append(x)
with open(os.path.join(R, 'victim-sec.csv'), 'w') as f:
    f.write('t_rel_s,ticks,ok,fail,p99_ok_ms,max_ms,last_status\n')
    for k in sorted(sec):
        e = sec[k]; ok = [x[2] for x in e if x[3] == 'OK']
        f.write('%d,%d,%d,%d,%s,%s,%s\n' % (k, len(e), len(ok), len(e) - len(ok), pct(ok, .99) if ok else '', max(x[2] for x in e), e[-1][3][:60]))
