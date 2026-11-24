#!/usr/bin/env python3
# B23 3-b confirm: victim per-second and per-phase summary. usage: python3 -I victimsum.py <run dir>
# Phases from driver.log: all-up (victim start .. n3 stop), n3-down (.. attack start L), attack (L .. stop rule), after (stop rule .. +60 s), teardown (harness stopping nodes).
# Per second (by request start): requests, ok, errors, p50/p99/max latency of the successes, error classes.
import sys, re, collections
d = sys.argv[1]
drv = open(f'{d}/logs/driver.log').read()
def t(pat):
    m = re.search(r'^(\d+\.\d+) \S+ ' + pat, drv, re.M); return float(m.group(1)) * 1000 if m else None
T_n3 = t('operator: stopping n3'); L = t('attack start'); S = t('stop: '); TD = t('stopall begin')
rows = []
for l in open(f'{d}/logs/victim.log'):
    f = l.split()
    if len(f) == 5 and f[0].isdigit(): rows.append((int(f[0]), f[1], int(f[2]), int(f[3]), f[4]))
if not rows: print('no victim rows'); sys.exit()
def phase(ms):
    if T_n3 and ms < T_n3: return '1 all-up'
    if L and ms < L: return '2 n3-down'
    if S and ms < S: return '3 attack'
    if TD and ms >= TD: return '5 teardown'
    return '4 after'
def pct(v, q):
    if not v: return '-'
    v = sorted(v); return v[min(len(v) - 1, int(q * len(v)))]
ph = collections.OrderedDict()
for r in rows: ph.setdefault(phase(r[0]), []).append(r)
print(f'# victim {d}: phases relative to attack start L (ms epoch {L}); stop rule at L+{(S - L) / 1000:.1f}s' if L and S else '# victim')
for k, rs in sorted(ph.items()):
    ok = [r for r in rs if r[2] == 1]; lat = [r[3] for r in ok]
    ec = collections.Counter(r[4] for r in rs if r[2] == 0)
    span = (rs[-1][0] - rs[0][0]) / 1000 + 1
    print(f'{k}: {len(rs)} req over {span:.0f}s, ok {len(ok)} ({100 * len(ok) / len(rs):.1f}%), lat p50 {pct(lat, .5)} p99 {pct(lat, .99)} max {max(lat) if lat else "-"} ms, errors {dict(ec)}')
print('# per second: t_rel_L_s req ok err p50 p99 max errclasses')
sec = collections.OrderedDict()
for r in rows: sec.setdefault(int((r[0] - (L or 0)) // 1000), []).append(r)
for s, rs in sec.items():
    ok = [r for r in rs if r[2] == 1]; lat = [r[3] for r in ok]
    ec = collections.Counter(r[4] for r in rs if r[2] == 0)
    print(s, len(rs), len(ok), len(rs) - len(ok), pct(lat, .5), pct(lat, .99), max(lat) if lat else '-', ','.join(f'{a}:{b}' for a, b in ec.items()) or '-')
