#!/usr/bin/env python3
"""B9 3-b confirm: readings of one lifetime (stage-2 b9peaks.py quantities, simplified).
X0 = median over the 30-s victim-only window of (NMT Other - JDK direct MemoryUsed); dU(t) = NMT Other(t) - JDK direct
(nearest JMX sample) - X0 (Netty's no-cleaner direct memory above idle). K = Client.RequestsSize. First OOM from
system.log (JVM Arguments line excluded); Netty 'used:' at failure."""
import sys, os, re, csv, time, statistics, calendar

R = sys.argv[1]
meta = {}
for l in open(os.path.join(R, 'run.meta')):
    p = l.split()
    if len(p) == 2 and p[1].isdigit(): meta.setdefault(p[0], int(p[1]))
a0 = meta['attack_start']
if meta.get('node_exit') and meta['node_exit'] >= meta.get('victim_end', 10 ** 15):
    meta['node_stopped_by_ctl'] = meta.pop('node_exit')
t_ref = a0; ref = 'attack_start'
for l in open(os.path.join(R, 'attack.log')):
    m = re.match(r'(BURST_START|HOLD_START|SEND_START) (\d+)', l)
    if m and m.group(1) in ('BURST_START', 'SEND_START'):
        t_ref = int(m.group(2)); ref = m.group(1)
    if m and m.group(1) == 'HOLD_START': meta['hold_start'] = int(m.group(2))
S = []
with open(os.path.join(R, 'samples.csv')) as f:
    for r in csv.DictReader(f):
        if r['heap_used'] in ('NA', '-1'): continue
        S.append({k: (int(v) if v.lstrip('-').isdigit() else None) for k, v in r.items()})
N = []
with open(os.path.join(R, 'nmt.csv')) as f:
    for r in csv.DictReader(f):
        try: N.append((int(r['epoch_ms']), int(r['other_committed_kb']) * 1024))
        except Exception: pass
MiB = 1 << 20


def near(t):
    return min(S, key=lambda s: abs(s['epoch_ms'] - t)) if S else None


base = [o - near(t)['direct_used'] for t, o in N if meta['victim_start'] <= t < a0]
X0 = statistics.median(base) if base else 0
dU = [(t, o - near(t)['direct_used'] - X0) for t, o in N if t >= a0]
print('reference %s = %d (attack_start %+.2f s)' % (ref, t_ref, (a0 - t_ref) / 1000))
print('X0 %.0f MiB (n=%d)' % (X0 / MiB, len(base)))
if dU:
    t, v = max(dU, key=lambda x: x[1]); print('dU_peak %.0f MiB at %+.1f s (NMT samples after attack start: %d)' % (v / MiB, (t - t_ref) / 1000, len(dU)))
A = [s for s in S if s['epoch_ms'] >= a0]
B = [s for s in S if meta['victim_start'] <= s['epoch_ms'] < a0]
def pk(col, scale=1, rows=A):
    v = [s[col] for s in rows if s.get(col) is not None and s[col] >= 0]
    return (max(v) / scale) if v else None
for col, sc, u in [('K_requests_size', MiB, 'MiB'), ('paused_conns', 1, ''), ('connected_clients', 1, ''), ('direct_used', MiB, 'MiB'),
                   ('heap_used', MiB, 'MiB'), ('ntr_active', 1, ''), ('ntr_pending', 1, '')]:
    print('%s peak %s %s (before attack: %s)' % (col, pk(col, sc), u, pk(col, sc, B)))
for col in ('protocol_exc', 'auth_success', 'auth_failure', 'req_dispatched', 'conn_paused_count'):
    v = [s[col] for s in A if s.get(col) is not None and s[col] >= 0]; b = [s[col] for s in B if s.get(col) is not None and s[col] >= 0]
    if v and b: print('%s delta during attack %d (before-window end %d)' % (col, max(v) - b[-1], b[-1]))
lastA = [s for s in A]
if lastA: print('last JMX sample %+.2f s: K %.0f MiB, paused %s, clients %s, direct %.0f MiB, heap %.0f MiB' % (
    (lastA[-1]['epoch_ms'] - t_ref) / 1000, lastA[-1]['K_requests_size'] / MiB, lastA[-1]['paused_conns'], lastA[-1]['connected_clients'],
    lastA[-1]['direct_used'] / MiB, lastA[-1]['heap_used'] / MiB))
fo = os.path.join(R, 'first-oom.txt')
if os.path.exists(fo) and os.path.getsize(fo):
    txt = open(fo).read()
    m = re.search(r'(ERROR|WARN|INFO)\s+\[([^\]]+)\]\s+(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d:\d\d),(\d{3})[^\n]*\n[^\n]*(OutOfMemoryError|OutOfDirectMemoryError)', txt)
    for l in txt.splitlines():
        if 'OutOfMemoryError' in l or 'OutOfDirectMemoryError' in l:
            print('first OOM line:', l.strip()[:300]); break
    if m:
        t = calendar.timegm(time.strptime(m.group(3) + ' ' + m.group(4), '%Y-%m-%d %H:%M:%S')) * 1000 + int(m.group(5))   # system.log is UTC
        print('first OOM record thread %s at %sT%s,%s UTC = %+.2f s after %s' % (m.group(2), m.group(3), m.group(4), m.group(5), (t - t_ref) / 1000, ref))
    u = re.search(r'used: (\d+), max: (\d+)', txt)
    if u: print('Netty counter at failure used %d (%.0f MiB) max %d (%.0f MiB)' % (int(u.group(1)), int(u.group(1)) / MiB, int(u.group(2)), int(u.group(2)) / MiB))
    st = [l.strip() for l in txt.splitlines() if l.strip().startswith('at ')][:8]
    print('stack top:', ' <- '.join(s[3:].split('(')[0] for s in st))
else:
    print('no OOM in system.log')
syslog = os.path.join(R, 'V-logs', 'system.log')
if os.path.exists(syslog):
    L = open(syslog, errors='replace').read()
    print('system.log counts: OutOfDirectMemoryError %d, "Force heap space OutOfMemoryError" %d, ERROR lines %d, WARN lines %d' % (
        L.count('OutOfDirectMemoryError'), L.count('Force heap space OutOfMemoryError'), len(re.findall(r'^ERROR ', L, re.M)), len(re.findall(r'^WARN ', L, re.M))))
if meta.get('node_exit'): print('node_exit %+.2f s after %s' % ((meta['node_exit'] - t_ref) / 1000, ref))
if os.path.exists(syslog):
    for l in open(syslog, errors='replace'):
        if 'Force heap space OutOfMemoryError' in l or 'Force heap space' in l:
            m = re.search(r'(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d:\d\d),(\d{3})', l)
            if m:
                t = calendar.timegm(time.strptime(m.group(1) + ' ' + m.group(2), '%Y-%m-%d %H:%M:%S')) * 1000 + int(m.group(3))
                print('forced heap OOM logged %+.2f s after %s: %s' % ((t - t_ref) / 1000, ref, l.strip()[:200]))
            break
