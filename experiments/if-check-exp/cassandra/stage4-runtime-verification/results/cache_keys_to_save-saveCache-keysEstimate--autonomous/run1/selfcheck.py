#!/usr/bin/env python3
"""Independent re-parse of the raw run files of cache_keys_to_save-saveCache-keysEstimate--autonomous.
usage: selfcheck.py <unit-dir (…/run1b/unit)> <cluster-dir (…/run1/cluster)>
Unit: re-derives min(N,P) from the STAGE4 save lines of test.out and from the 'Saved … (n items)' lines of the test log copy
(saved-log-lines.txt), and compares file lengths with per-item cost. Cluster: re-derives, from system.log 'Saved' lines and the
times of the setters in session.log (not from phases.jsonl), the item counts per window; compares with the stress outputs'
error counts and the warm-load counts. Prints PASS/FAIL lines."""
import calendar, json, re, sys, time, os
unit, clus = sys.argv[1], sys.argv[2]
fails = 0
def res(ok, msg):
    global fails
    fails += (not ok)
    print(('PASS ' if ok else 'FAIL ') + msg)

# ---------------- unit
rows = []
for l in open(unit + '/test.out'):
    if l.startswith('STAGE4 save '):
        rows.append(dict(kv.split('=') for kv in l.split()[2:]))
res(len(rows) == 14 + 12, f'unit: {len(rows)} save rows (key 7 N x 2 reps = 14, row 3x2 + counter 3x2 = 12)')
bad = []
for r in rows:
    n, p = int(r['N']), int(r['P'])
    want = p if (n == 0 or n >= p) else n
    if not (int(r['completed']) == want and int(r['loaded']) == want and int(r['sizeAfterLoad']) == want and int(r['live']) == p and int(r['liveAfterSave']) == p):
        bad.append(r)
res(not bad, f'unit: every row completed==loaded==size==min(N,P), live unchanged by the save ({len(bad)} bad)')
# log lines: sequence of 'Saved <Cache> (n items)' must contain each expected count; every logged count <= its population
logl = [re.match(r'Saved (\w+) \((\d+) items\)', l) for l in open(unit + '/saved-log-lines.txt')]
logl = [(m.group(1), int(m.group(2))) for m in logl if m]
pops = {'KeyCache': 10000, 'RowCache': 2000, 'CounterCache': 2000}
res(all(i <= pops[c] for c, i in logl if c != 'KeyCache' or True), f'unit log: all {len(logl)} "Saved" lines have items <= population')
# the log has two Saved lines per (cache,N,rep): submitWrite path and direct Writer; compare the multiset with the rows
from collections import Counter
want = Counter()
for r in rows:
    n, p = int(r['N']), int(r['P'])
    c = {'key': 'KeyCache', 'row': 'RowCache', 'counter': 'CounterCache'}[r['cache']]
    want[(c, p if (n == 0 or n >= p) else n)] += 2
got = Counter(logl)
extra = {k: v for k, v in got.items() if k not in want}
short = {k: (want[k], got.get(k, 0)) for k in want if got.get(k, 0) < want[k]}
res(not short, f'unit log: each expected (cache, items) pair appears at least as often as the rows imply (short: {short})')
print('INFO unit log pairs not from the sweep (race/hot-check/control saves):', dict(extra))
# per-item cost of the key cache file: len = a + b*items, same for both reps and all N
pts = sorted({(int(r['completed']), int(r['fileLen'])) for r in rows if r['cache'] == 'key'})
if len(pts) >= 3:
    (i0, l0), (i1, l1) = pts[1], pts[-1]
    b = (l1 - l0) / (i1 - i0)
    dev = max(abs(l - (l0 + b * (i - i0))) / l for i, l in pts[1:])
    res(dev < 0.01, f'unit: key file length linear in items (per-item {b:.2f} B, max deviation {dev*100:.2f}%) over {pts}')
# ---------------- cluster
import datetime
def local_epoch(s):  # session.log "[2026-10-26 15:25:16]" local time
    return time.mktime(time.strptime(s, '%Y-%m-%d %H:%M:%S'))
sys_lines = []
for l in open(clus + '/system.log', errors='replace'):
    m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),\d+ AutoSavingCache.java:\d+ - Saved (\w+) \((\d+) items\)', l)
    if m:
        t = calendar.timegm(time.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S'))
        sys_lines.append((t, m.group(2), int(m.group(3))))
sys_lines.sort()
res(len(sys_lines) > 30, f'cluster: {len(sys_lines)} Saved lines in system.log')
ev = []
for l in open(clus + '/session.log'):
    m = re.match(r'\[(.+?)\] (nodetool setcachekeystosave (\d+) (\d+) (\d+)|nodetool setcachecapacity .*|=== .*)$', l.strip())
    if m:
        ev.append((local_epoch(m.group(1)), m.group(2), int(m.group(3)) if m.group(3) else None))
for e in ev: print('INFO event', time.strftime('%H:%M:%S', time.localtime(e[0])), e[1])
start = None
m = re.search(r'\[(.+?)\] === L1', open(clus + '/session.log').read())
t_l1 = local_epoch(m.group(1)) if m else 0
# the "all" window: from L1 start to the first setter; population E per cache = the plateau value (max items seen with the yaml unset)
setters = [e for e in ev if e[2] is not None]
first_set = setters[0][0]
E = {}
for c in ('KeyCache', 'RowCache', 'CounterCache'):
    vals = [i for t, cc, i in sys_lines if cc == c and t_l1 <= t < first_set]
    E[c] = vals[-1] if vals else None
    res(bool(vals) and vals[-1] >= 0.99 * max(vals[-3:]), f"cluster: {c} yaml-unset population (last save) {E[c]}, last 3 {vals[-3:]} (the counter cache is at its 50 MiB cap and still settling after the workload; later N=0 windows must equal this value)")
# windows per setter: lines from t+PERIOD+2 .. next event (setcache* or ===) must all equal min(N, E) (N=0: E)
allev = sorted(ev)
for idx, (t, txt, n) in enumerate(allev):
    if n is None:
        continue
    nxt = next((t2 for t2, tx, _ in allev[idx + 1:]), None) or 1e12
    # skip the capacity event's window (population changes) but report it
    for c in ('KeyCache', 'RowCache', 'CounterCache'):
        win = [i for tt, cc, i in sys_lines if cc == c and t + 9 <= tt < nxt]
        if not win or E[c] is None:
            res(False, f'cluster: window N={n} {c}: no saves'); continue
        want = E[c] if (n == 0 or n >= E[c]) else n
        res(all(i == want for i in win), f'cluster: setter N={n} at {time.strftime("%H:%M:%S", time.localtime(t))}: {c} {len(win)} saves all == {want} (values {sorted(set(win))})')
# yaml-set windows (restart lifetimes): the last two saves of each cache in the window are the yaml N (population is larger)
for idx, (t, txt, n) in enumerate(allev):
    mm = re.match(r'=== yaml(\d+):', txt)
    if not mm:
        continue
    yn = int(mm.group(1)); nxt = allev[idx + 1][0] if idx + 1 < len(allev) else 1e12
    for c in ('KeyCache', 'RowCache', 'CounterCache'):
        win = [i for tt, cc, i in sys_lines if cc == c and t <= tt < nxt]
        res(len(win) >= 1 and win[-1] == yn, f"cluster: yaml N={yn} lifetime: {c} last save {win[-3:]} ends at {yn}")
l4 = [e for e in allev if e[1].startswith('=== L4')]
if l4:
    res(not [1 for tt, cc, i in sys_lines if tt >= l4[0][0]], 'cluster: no Saved line after the L4 start (periods 0)')
# warm load counts after restarts
txt = open(clus + '/system.log', errors='replace').read()
for m in re.finditer(r'Completed loading \((\d+) ms; (\d+) keys\) (\w+) cache', txt):
    print('INFO warm load:', m.group(3), m.group(2), 'keys')
# stress errors
for f in sorted(os.listdir(clus)):
    if f.startswith('stress-') and f.endswith('.out'):
        o = open(os.path.join(clus, f)).read()
        m = re.search(r'Total errors\s*:\s*(\d+)', o)
        res(m is not None and int(m.group(1)) == 0, f'cluster: {f} total errors {m.group(1) if m else "?"}')
print('SELFCHECK', 'FAILS=%d' % fails)
sys.exit(1 if fails else 0)
