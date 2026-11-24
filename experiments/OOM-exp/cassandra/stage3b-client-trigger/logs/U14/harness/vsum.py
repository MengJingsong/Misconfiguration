#!/usr/bin/env python3
"""U14 3-b confirm: victim view of one lifetime. usage: vsum.py <logs dir>/<label>  -> JSON on stdout, per-second CSV to
<dir>/victim-per-second.csv and a per-minute table to <dir>/victim-per-minute.txt.
Phases (from summary.json): before = victim start .. attack_start_ms (restart: victim start .. restart_up_ms); during = attack
start .. node death (or the client's end); after = node death .. victim stop. Ops are binned by issue time. Latency only of ok
ops. 'cp' marks seconds inside a checkpoint (two forced full GCs by jcmd; a diagnostic aid, not the attack)."""
import json, os, sys, time, statistics

d = sys.argv[1]
S = json.load(open(d + '/summary.json'))
os.environ['TZ'] = 'America/New_York'; time.tzset()
ops = []
for l in open(d + '/victim.csv'):
    p = l.strip().split(',')
    if len(p) == 4 and p[0].isdigit() and p[1] in ('read', 'write'):
        ops.append((int(p[0]), p[1], float(p[2]), p[3]))
ops.sort()
cps = []
try:
    for l in open(d + '/checkpoints.jsonl'):
        c = json.loads(l)
        cps.append((c['ms'] - int(c.get('secs', 0) * 1000), c['ms']))
except OSError:
    pass
a0 = S.get('attack_start_ms') or S.get('restart_up_ms') or S.get('restart_begin_ms')
dead = S.get('node_dead_ms')
cl = [v for k, v in S.items() if k.startswith('client ') and isinstance(v, dict)]
end_client = None
if cl and cl[-1].get('last_ok_ms'):
    end_client = cl[-1]['last_ok_ms']
t_end_attack = dead or end_client or (ops[-1][0] if ops else None)


def phase(t):
    if a0 and t < a0:
        return 'before'
    if t_end_attack and t >= t_end_attack and dead:
        return 'after'
    return 'during'


def stats(xs):
    n = len(xs)
    ok = [x for x in xs if x[3] == 'ok']
    lat = sorted(x[2] for x in ok)
    errs = {}
    for x in xs:
        if x[3] != 'ok':
            errs[x[3]] = errs.get(x[3], 0) + 1
    q = lambda p: round(lat[min(len(lat) - 1, int(p * len(lat)))], 1) if lat else None
    return {'ops': n, 'ok': len(ok), 'ok_pct': round(100.0 * len(ok) / n, 2) if n else None, 'errors': errs,
            'p50_ms': q(0.5), 'p99_ms': q(0.99), 'max_ms': round(lat[-1], 1) if lat else None,
            'secs': round((xs[-1][0] - xs[0][0]) / 1000.0) if xs else 0}


out = {'label': os.path.basename(d.rstrip('/')), 'attack_start_ms': a0, 'node_dead_ms': dead, 'client_last_ok_ms': end_client}
for ph in ('before', 'during', 'after'):
    out[ph] = stats([o for o in ops if phase(o[0]) == ph])
incp = lambda t: any(s <= t <= e for s, e in cps)
dur = [o for o in ops if phase(o[0]) == 'during']
out['during_outside_checkpoints'] = stats([o for o in dur if not incp(o[0])])
out['during_inside_checkpoints'] = stats([o for o in dur if incp(o[0])])
# per second
bins = {}
for o in ops:
    bins.setdefault(o[0] // 1000, []).append(o)
with open(d + '/victim-per-second.csv', 'w') as f:
    f.write('sec,phase,cp,ops,ok,err,p50_ms,max_ms\n')
    for s in sorted(bins):
        xs = bins[s]; ok = [x[2] for x in xs if x[3] == 'ok']
        f.write(f"{s},{phase(s*1000)},{int(incp(s*1000))},{len(xs)},{len(ok)},{len(xs)-len(ok)},"
                f"{round(statistics.median(ok),1) if ok else ''},{round(max(ok),1) if ok else ''}\n")
# first second (during) with < 50 % ok, and the longest run of seconds with 0 ok
secs = sorted(s for s in bins if phase(s * 1000) == 'during')
first_bad = next((s for s in secs if sum(1 for x in bins[s] if x[3] == 'ok') < 0.5 * len(bins[s])), None)
out['first_during_second_below_50pct_ok'] = time.strftime('%T', time.localtime(first_bad)) if first_bad else None
out['first_bad_s_after_attack_start'] = round(first_bad - a0 / 1000.0) if (first_bad and a0) else None
# per minute (during + after)
mins = {}
for o in ops:
    mins.setdefault(o[0] // 60000, []).append(o)
with open(d + '/victim-per-minute.txt', 'w') as f:
    f.write('minute(NY)  phase   ops   ok%    p50ms    p99ms    maxms  errors\n')
    for m in sorted(mins):
        xs = mins[m]; st = stats(xs)
        f.write(f"{time.strftime('%H:%M', time.localtime(m*60))}  {phase(m*60000):7s} {st['ops']:5d} {st['ok_pct'] if st['ok_pct'] is not None else '':>6} "
                f"{str(st['p50_ms']):>8} {str(st['p99_ms']):>8} {str(st['max_ms']):>8}  {json.dumps(st['errors'])}\n")
print(json.dumps(out))
