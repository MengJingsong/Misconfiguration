#!/usr/bin/env python3
"""victim-summary.py <run dir>: the victim role's view of a U7 3-b confirm run. Reads victim.csv (t_send_ms,op,outcome,
latency_ms), client.txt (attack t_send) and driver.txt (OOM line first seen, OOM endpoint, daemon stopped). Writes
victim-persec.csv (per second relative to the attack send: ops, ok, err, skip, ok-latency p50/p99/max) and prints per-phase
aggregates: before (victim start .. send), during (send .. OOM line), after-OOM (OOM line .. daemon stopped), stopped."""
import datetime, os, re, sys
from collections import defaultdict
R = sys.argv[1]
rd = lambda n: open(os.path.join(R, n), errors='replace').read() if os.path.exists(os.path.join(R, n)) else ''


def dt(s):
    return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000


def ev(pat):
    m = re.search(r'^(\S+) .*' + pat, rd('driver.txt'), re.M)
    return dt(m.group(1)) if m else None


m = re.search(r't_send=(\d+)', rd('client.txt'))
t_send = int(m.group(1)) if m else None
t_oom = ev('OOM line first seen')
t_endp = ev('OOM endpoint')
t_stop = ev('daemon stopped')
m = re.search(r't_end=(\d+) latency_ms=(\d+) outcome=(.*)', rd('client.txt'))
print('attack send %s; attack client end %s (%s); OOM line first seen %s; endpoint (dump written) %s; daemon stopped %s' % (
    t_send, m.group(1) if m else None, m.group(3)[:120] if m else None, t_oom, t_endp, t_stop))
ops = []
for l in rd('victim.csv').splitlines():
    if not l or l[0] == '#':
        continue
    t, op, out, lat = l.split(',')
    ops.append((int(t), op, out, int(lat)))
ops.sort()
if not ops or t_send is None:
    print('no victim ops or no send'); sys.exit(0)


def pct(v, p):
    if not v: return None
    v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))]


def agg(sel):
    n = len(sel); ok = [o for o in sel if o[2] == 'ok']; err = defaultdict(int)
    for o in sel:
        if o[2] != 'ok': err[o[2]] += 1
    lat = [o[3] for o in ok]
    return n, len(ok), dict(err), pct(lat, .5), pct(lat, .99), max(lat) if lat else None


# 'during' ends at the OOM line; without an OOM, at the attack request's end when the server answered it (not a
# client-side connection loss); otherwise at the daemon stop.
t_cend = int(m.group(1)) if m else None
lost = m and re.match(r'ERR (NoHostAvailable|ConnectionShutdown|OperationTimedOut|ConnectionException)', m.group(3))
if t_oom:
    end_during, after_name = t_oom, 'after-OOM (daemon up)'
elif t_cend and not lost:
    end_during, after_name = t_cend, 'after attack end (up)'
else:
    end_during, after_name = t_stop or ops[-1][0] + 1, 'after (daemon up)'
phases = [('before', ops[0][0], t_send), ('during', t_send, end_during),
          (after_name, end_during, t_stop or ops[-1][0] + 1), ('stopped', t_stop or ops[-1][0] + 1, ops[-1][0] + 1)]
for name, a, b in phases:
    sel = [o for o in ops if a <= o[0] < b]
    n, ok, err, p50, p99, mx = agg(sel)
    print('%-22s %6.1f s  ops %5d  ok %5d (%5.1f %%)  err %s  ok-latency ms p50 %s p99 %s max %s' % (
        name, (b - a) / 1000, n, ok, 100.0 * ok / n if n else 0, err, p50, p99, mx))
# per second
bins = defaultdict(list)
for o in ops:
    bins[(o[0] - t_send) // 1000].append(o)
with open(os.path.join(R, 'victim-persec.csv'), 'w') as f:
    f.write('sec_from_send,ops,ok,err,skip,p50_ms,p99_ms,max_ms\n')
    for s in sorted(bins):
        sel = bins[s]; n, ok, err, p50, p99, mx = agg(sel)
        sk = err.get('skip', 0)
        f.write('%d,%d,%d,%d,%d,%s,%s,%s\n' % (s, n, ok, n - ok - sk, sk, p50, p99, mx))
# first second where the victim's ok-rate dropped below 50 %
bad = [s for s in sorted(bins) if s >= 0 and sum(1 for o in bins[s] if o[2] == 'ok') < 0.5 * len(bins[s])]
print('first second (from send) with victim ok < 50 %%: %s' % (bad[0] if bad else 'none'))
ok_after = [s for s in sorted(bins) if bad and s > bad[0] and all(o[2] == 'ok' for o in bins[s])]
print('first fully-ok second after that: %s' % (ok_after[0] if ok_after else 'none'))
