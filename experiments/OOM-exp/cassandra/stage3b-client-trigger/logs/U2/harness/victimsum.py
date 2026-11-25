#!/usr/bin/env python3
"""U2 3-b confirm (2026-11-24): victimsum.py <run log dir>: the victim role's view per window.
Windows (ms): before = victim start .. attack client start (exit.txt t_client_ms); during = attack start .. first
OutOfDirectMemoryError in system*.log (UTC timestamps; else the watcher's t_oom); oom->exit = .. node exit (t_exit);
after = node exit .. victim stop. Persistent-connection requests (W/R, 20/s, 2 s timeout; 'missed'/'down' ticks count as
failures) and new-connection logins (N, every 5 s) are reported separately. Writes victim-persec.txt
(second relative to the attack start: ticks, ok, fail, p50 ms, max ms, N ok/fail)."""
import datetime, glob, os, re, sys
R = sys.argv[1]
ex = dict(l.strip().split('=', 1) for l in open(os.path.join(R, 'exit.txt')) if '=' in l)
a0 = int(ex['t_client_ms'])
t_oom_line = None
for f in sorted(glob.glob(os.path.join(R, 'system*.log*'))):
    for l in open(f, errors='replace'):
        m = re.search(r'(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d:\d\d),(\d{3})', l)
        if m and ('failed to allocate' in l or 'OutOfMemory error letting' in l or 'OutOfDirectMemoryError' in l or 'java.lang.OutOfMemoryError' in l):
            if True:
                t = datetime.datetime.strptime(m.group(1) + ' ' + m.group(2), '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
                v = int(t.timestamp() * 1000) + int(m.group(3))
                t_oom_line = v if t_oom_line is None else min(t_oom_line, v)
            break
t_oom = t_oom_line or (int(ex['t_oom']) * 1000 if ex.get('t_oom') else None)
t_exit = int(ex['t_exit']) * 1000 if ex.get('t_exit') else None
rows = []
for l in open(os.path.join(R, 'victim.txt'), errors='replace'):
    if l.startswith('#') or not l.strip():
        continue
    p = l.split()
    rows.append((int(p[0]), p[1], int(p[2]), p[3]))
def win(t):
    if t < a0: return 'before'
    if t_oom is None or t < t_oom: return 'during'
    if t_exit is None or t < t_exit: return 'oom->exit'
    return 'after'
def pct(v, q):
    v = sorted(v); return v[min(len(v) - 1, int(q * len(v)))] if v else 0
print('attack start %d; first OOM line %s (%s s after attack start); node exit %s (%s s)' % (
    a0, t_oom, '%+.1f' % ((t_oom - a0) / 1000) if t_oom else '-', t_exit, '%+.1f' % ((t_exit - a0) / 1000) if t_exit else '-'))
for kind, sel in (('persistent W/R', lambda r: r[1] != 'N'), ('new-connection login N', lambda r: r[1] == 'N')):
    for w in ('before', 'during', 'oom->exit', 'after'):
        rs = [r for r in rows if sel(r) and win(r[0]) == w]
        if not rs:
            print('%-22s %-9s: no ticks' % (kind, w)); continue
        ok = [r for r in rs if r[3] == 'OK']; lat = [r[2] for r in ok]
        errs = {}
        for r in rs:
            if r[3] != 'OK':
                k = re.sub(r'[0-9]+', 'N', r[3])[:60] if r[1] not in ('-',) else r[3]; errs[k] = errs.get(k, 0) + 1
        print('%-22s %-9s: %.1f s, %d, OK %d (%.1f%%), OK ms p50 %d p99 %d max %d; failures: %s' % (
            kind, w, (rs[-1][0] - rs[0][0]) / 1000, len(rs), len(ok), 100.0 * len(ok) / len(rs), pct(lat, .5), pct(lat, .99),
            max(lat) if lat else 0, ', '.join('%s x%d' % kv for kv in sorted(errs.items(), key=lambda x: -x[1])) or 'none'))
pr = [r for r in rows if r[1] != 'N']
okd = [r for r in pr if r[0] >= a0 and r[3] == 'OK']
fail = [r for r in pr if r[0] >= a0 and r[3] != 'OK']
if okd: print('last persistent OK after attack start: %+.1f s' % ((okd[-1][0] - a0) / 1000))
if fail: print('first persistent failure after attack start: %+.1f s (%s)' % ((fail[0][0] - a0) / 1000, fail[0][3][:60]))
by = {}
for t, op, lat, st in rows:
    s = (t - a0) // 1000
    v = by.setdefault(s, [0, 0, 0, [], 0, 0])
    if op == 'N':
        v[4 if st == 'OK' else 5] += 1; continue
    v[0] += 1
    if st == 'OK': v[1] += 1; v[3].append(lat)
    else: v[2] += 1
with open(os.path.join(R, 'victim-persec.txt'), 'w') as f:
    f.write('# sec_rel_attack ticks ok fail p50_ms max_ms N_ok N_fail\n')
    for s in sorted(by):
        v = by[s]; f.write('%d %d %d %d %d %d %d %d\n' % (s, v[0], v[1], v[2], pct(v[3], .5), max(v[3]) if v[3] else 0, v[4], v[5]))
