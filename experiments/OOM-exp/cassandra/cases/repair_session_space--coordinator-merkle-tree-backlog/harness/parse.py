#!/usr/bin/env python3
# C7 run parser (design §2.6). parse.py <run dir>   (on ms0625; reads n1-logs/, samples.csv, cg.csv, n?-trees.txt, args.txt)
# U_trees: held sets(t) = received(t) - 2 x released jobs(t) (system.log `Received merkle tree`, `Created k sync tasks based
# on 2 merkle tree responses`); held bytes ~ held sets x mean m (m = sum of logged off-heap allocations / allocations).
# U_direct from the JMX sampler; per-instance validation progress from `Created ... merkle trees` debug lines.
import sys, os, re, csv, datetime, collections
R = sys.argv[1]; MiB = 1048576.0
def ts(line):
    m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3})', line)
    if not m: return None
    return datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000 + int(m.group(2))
args = open(os.path.join(R, 'args.txt')).read()
rs = int(re.search(r'(\d+) repair start', args).group(1)); m_ = re.search(r'(\d+) repair end', args); re_ = int(m_.group(1)) if m_ else None
ev = []; allocs = []; sessions = set(); recv_by = collections.Counter(); own = []
for l in open(os.path.join(R, 'n1-logs', 'system.log'), errors='replace'):
    t = ts(l)
    if t is None or t < rs - 5000: continue
    if 'Received merkle tree for' in l:
        ev.append((t, +1)); recv_by[re.search(r'from (\S+)', l).group(1)] += 1
    elif re.search(r'Created \d+ sync tasks based on \d+ merkle tree responses', l): ev.append((t, -2))
    elif 'new session: will sync' in l: sessions.add(re.search(r'repair #([0-9a-f-]+)', l).group(1))
for l in open(os.path.join(R, 'n1-logs', 'debug.log'), errors='replace'):
    t = ts(l)
    if t is None or t < rs - 5000: continue
    if 'for an off-heap merkle tree' in l: allocs.append((t, int(re.search(r'size (\d+)', l).group(1))))
    elif 'merkle trees with merkle trees size' in l: own.append((t, l))
ev.sort(); held = 0; peak = (0, 0); recv = 0; rel = 0
for t, d in ev:
    held += d; recv += d if d > 0 else 0; rel += 1 if d < 0 else 0
    if held > peak[0]: peak = (held, t)
na = len(allocs); sa = sum(s for _, s in allocs); m = sa / recv if recv else 0   # m = per received tree SET (one buffer per range tree)
def leaves(lines):
    out = []
    for t, l in lines:
        mm = re.search(r'merkle trees size (\d+), (\d+) partitions, (\d+) bytes', l)
        if mm: out.append((t, int(mm.group(2)), int(mm.group(2)), int(mm.group(3))))   # (t, partitions, partitions, bytes)
    return out
ownl = leaves(own)
peer = {}
for n in ('n2', 'n3', 'n4'):
    p = os.path.join(R, n + '-trees.txt')
    if os.path.exists(p):
        pl = leaves([(ts(l), l) for l in open(p, errors='replace') if ts(l) and ts(l) >= rs - 5000])
        peer[n] = pl
rows = list(csv.DictReader(open(os.path.join(R, 'samples.csv'))))
def f(r, k):
    try: v = float(r[k]); return v if v >= 0 else None
    except: return None
good = [r for r in rows if f(r, 'direct_used') is not None]
pre = [r for r in good if int(r['epoch_ms']) <= rs] or good[:3]
base = min(f(r, 'direct_used') for r in pre) if pre else 0
upk = max(good, key=lambda r: f(r, 'direct_used')) if good else None
hpk = max((f(r, 'heap_used') or 0) for r in good) if good else 0
npk = max((f(r, 'net_pool_size') or 0) for r in good) if good else 0
last = good[-1] if good else None
dead = next((int(r['epoch_ms']) for r in rows if r['direct_used'] == 'NA' and int(r['epoch_ms']) > rs), None)
rel_s = lambda t: (t - rs) / 1000.0
print('sessions=%d received=%d (by endpoint: %s) released_jobs=%d | held_sets_peak=%d at +%.0fs' % (len(sessions), recv, dict(recv_by), rel, peak[0], rel_s(peak[1]) if peak[1] else 0))
print('offheap allocs n1 (one per range tree): n=%d sum=%.1f MiB; m per set = sum/received = %.2f MiB (~%.0f leaves at 82 B); single buffer min=%.2f max=%.2f MiB | held bytes at peak ~ held_sets x m = %.0f MiB' % (
    na, sa / MiB, m / MiB, m / 82.0, (min(s for _, s in allocs) / MiB) if na else 0, (max(s for _, s in allocs) / MiB) if na else 0, peak[0] * m / MiB))
print('n1 own validations=%d (partitions mean %.0f, last at +%.0fs); ' % (len(ownl), sum(x[1] for x in ownl) / max(1, len(ownl)), rel_s(ownl[-1][0]) if ownl else -1) +
      '; '.join('%s validations=%d last at +%.0fs partitions mean %.0f max %d' % (n, len(v), rel_s(v[-1][0]) if v else -1, sum(x[1] for x in v) / max(1, len(v)), max([x[1] for x in v] or [0])) for n, v in peer.items()))
if upk:
    print('U_direct: base=%.1f MiB peak=%.1f MiB at +%.0fs (count %s) | last sample %.1f MiB at +%.0fs | heap_peak=%.0f MiB net_pool_peak=%.1f MiB%s' % (
        base / MiB, f(upk, 'direct_used') / MiB, rel_s(int(upk['epoch_ms'])), upk['direct_count'], f(last, 'direct_used') / MiB, rel_s(int(last['epoch_ms'])), hpk / MiB, npk / MiB,
        (' | n1 down (NA) at +%.0fs' % rel_s(dead)) if dead else ''))
if re_: print('repair duration %.0fs' % rel_s(re_))
# held sets x m vs direct - base, at the U_direct peak
if upk:
    tp = int(upk['epoch_ms']); h = 0
    for t, d in ev:
        if t <= tp: h += d
    print('at U_direct peak: held_sets=%d, held_sets x m = %.0f MiB, U_direct - base = %.0f MiB, net_pool=%.1f MiB' % (h, h * m / MiB, (f(upk, 'direct_used') - base) / MiB, (f(upk, 'net_pool_size') or 0) / MiB))
# timeline every 15 s
print('timeline (+s held_sets direct_MiB val_n1):')
tl = []
for r in good[::15]:
    t = int(r['epoch_ms'])
    if t < rs: continue
    h = sum(d for te, d in ev if te <= t); vo = sum(1 for x in ownl if x[0] <= t)
    tl.append('+%d:%d/%.0f/%d' % (rel_s(t), h, f(r, 'direct_used') / MiB, vo))
print(' '.join(tl))
