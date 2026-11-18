#!/usr/bin/env python3
"""U3 per-run analysis (design §2.6 O1, O5, O7 and §2.7 endpoint rules). usage: analyze.py <run logs dir>
O1 from gc-pauses.log (unrotated -Xlog:gc, time+uptime): peak post-GC heap, pauses, Full, To-space exhausted, humongous,
   max fraction of wall time in STW pauses over any 60 s window (service-loss rule: >= 90 %).
O5 from memory.txt: max memory.current, oom_kill, max RssAnon.
O7 from clients/r.*: reads ok/error by type, items delivered, actual in-flight reads per second (max/mean), first 10 s apart.
Endpoint: OOM = daemon died + OutOfMemoryError in node.out/system.log + oom_kill 0; cgroup kill or other death = invalid;
survival = window completed; < 1 read per client = invalid (workload did not run)."""
import glob, os, re, sys
from collections import Counter

L = sys.argv[1]
summ = open(os.path.join(L, 'summary-raw.txt')).read()


def g(pat, default=None):
    mm = re.search(pat, summ)
    return mm.group(1) if mm else default


c = int(g(r' c=(\d+)', '0')); win = int(g(r'window=(\d+)', '180'))
t_cl = float(g(r'CLIENTS start epoch=([\d.]+)', '0'))
died = 'OUTCOME-RAW died' in summ
# ---- GC
pauses = []  # (uptime_end_s, dur_s, line)
peak_after = 0.0; full = tos = hum = 0; first_up = None; t_wall0 = None
rx = re.compile(r'\[([^\]]+)\]\[([\d.]+)s\].*?GC\(\d+\) (Pause [^(]*\([^)]*\)(?: \([^)]*\))?).*?(\d+)M->(\d+)M\((\d+)M\) ([\d.]+)ms')
gl = os.path.join(L, 'gc-pauses.log')
lines = open(gl, errors='replace').read().splitlines() if os.path.exists(gl) else []
from datetime import datetime
for ln in lines:
    if 'To-space exhausted' in ln:
        tos += 1
    if 'Humongous' in ln and 'Pause' in ln:
        hum += 1
    mm = rx.search(ln)
    if not mm:
        continue
    ts, up, kind, b, a, cap, ms = mm.groups()
    up = float(up); dur = float(ms) / 1000.0
    try:
        wall = datetime.strptime(ts[:23], '%Y-%m-%dT%H:%M:%S.%f').timestamp()
    except Exception:
        wall = None
    if wall is not None and t_wall0 is None:
        t_wall0 = wall - up
    pauses.append((up, dur, kind, int(b), int(a), int(cap), wall))
    if 'Full' in kind:
        full += 1
    if wall is None or wall >= t_cl:
        peak_after = max(peak_after, int(a))
# service loss: max pause fraction over 60 s windows (ending at each pause end)
maxfrac = 0.0
if pauses:
    for i, (up, d, *_r) in enumerate(pauses):
        lo = up - 60.0
        s = sum(min(dd, uu - lo) for uu, dd, *_x in pauses if lo < uu <= up)
        maxfrac = max(maxfrac, s / 60.0)
last = pauses[-5:]
# ---- memory
mx = 0; oomk = '0'; rss = 0
for ln in open(os.path.join(L, 'memory.txt')) if os.path.exists(os.path.join(L, 'memory.txt')) else []:
    p = ln.split()
    if len(p) >= 3 and p[1] != 'end':
        try:
            mx = max(mx, int(p[1])); rss = max(rss, int(p[3]) if len(p) > 3 else 0)
        except ValueError:
            pass
    if len(p) >= 3:
        oomk = p[2]
# ---- clients
recs = []
for fn in glob.glob(os.path.join(L, 'clients', 'r.*')):
    for ln in open(fn):
        p = ln.split()
        if len(p) >= 8:
            recs.append((int(p[0]), int(p[1]), float(p[2]), float(p[3]), p[4], int(p[5]), int(p[6]), p[7]))
ok = [r for r in recs if r[4] == 'ok']
errs = Counter(r[7] for r in recs if r[4] != 'ok')
items = sum(r[5] for r in ok)
t_end_all = max([r[3] for r in recs] + [t_cl])
span = max(1.0, t_end_all - t_cl)
infl = []
if recs:
    for s in range(int(t_cl), int(t_end_all) + 1):
        infl.append(sum(1 for r in recs if r[2] <= s + 0.5 < r[3]))
lat = sorted(r[3] - r[2] for r in ok)
first10 = sum(1 for r in ok if r[3] <= t_cl + 10)
per_client = Counter(r[0] for r in ok)
nodeout = open(os.path.join(L, 'node.out'), errors='replace').read() if os.path.exists(os.path.join(L, 'node.out')) else ''
syslog = open(os.path.join(L, 'system.log'), errors='replace').read() if os.path.exists(os.path.join(L, 'system.log')) else ''
oom_msg = re.findall(r'OutOfMemoryError: ([^\n]*)', nodeout + syslog)
t_death = g(r'DAEMON DIED at epoch=([\d.]+)')
hprof = glob.glob(os.path.join(L, '*.hprof'))
if died:
    if oomk not in ('0', '', None):
        outcome = 'invalid (cgroup oom_kill=%s)' % oomk
    elif oom_msg:
        outcome = 'OOM (%s)' % oom_msg[0].strip()
    else:
        outcome = 'invalid (died without OutOfMemoryError)'
else:
    outcome = 'survived'
if len(per_client) < c and not died and len(ok) < c:
    outcome += ' [WARNING: fewer than 1 completed read per client]'
print('RUN %s' % os.path.basename(os.path.dirname(L)))
print('OUTCOME %s; t_death_after_clients=%s s; hprof=%s' % (outcome, ('%.1f' % (float(t_death) - t_cl)) if t_death else '-',
                                                        ','.join('%s(%d B)' % (os.path.basename(h), os.path.getsize(h)) for h in hprof) or '-'))
print('GC pauses=%d full=%d to_space_exhausted_lines=%d humongous_pauses=%d peak_postGC_after_clients=%d MB max_60s_pause_fraction=%.2f'
      % (len(pauses), full, tos, hum, peak_after, maxfrac))
print('GC last: ' + ' | '.join('%s %d->%d(%d)M %.0fms' % (k.strip(), b, a, cp, d * 1000) for (u, d, k, b, a, cp, w) in last))
print('MEM max_memory.current=%.2f GB max_RssAnon=%.2f GB oom_kill=%s' % (mx / 2**30, rss / 2**20, oomk))
print('CLIENTS c=%d reads_total=%d ok=%d errors=%s items_delivered=%d items_per_s=%.0f span=%.1f s ok_in_first_10s=%d clients_with_ok=%d'
      % (c, len(recs), len(ok), dict(errs), items, items / span, span, first10, len(per_client)))
if lat:
    print('LATENCY ok reads: p50=%.2f s p90=%.2f s max=%.2f s' % (lat[len(lat) // 2], lat[int(len(lat) * 0.9)], lat[-1]))
if infl:
    print('INFLIGHT reads per second: max=%d mean=%.1f' % (max(infl), sum(infl) / len(infl)))
for h in hprof:
    st = os.stat(h)
    birth = getattr(st, 'st_birthtime', None)
    if birth is None:
        import subprocess
        try:
            birth = float(subprocess.check_output(['stat', '-c', '%W', h]).decode().strip())
        except Exception:
            birth = None
    print('OOM_INSTANT hprof created at t=%s s (first OutOfMemoryError; dump start), dump end t=%.1f s, daemon death t=%s s (after clients start)'
          % (('%.1f' % (birth - t_cl)) if birth else '-', st.st_mtime - t_cl, ('%.1f' % (float(t_death) - t_cl)) if t_death else '-'))
print('OOMMSG %s' % (oom_msg[:2]))
