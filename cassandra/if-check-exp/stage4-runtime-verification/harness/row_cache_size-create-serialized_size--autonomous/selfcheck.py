#!/usr/bin/env python3
"""Independent self-check: re-parses the RAW files (not the analyzers' output) and recomputes the facts the conclusion rests on.
Usage: selfcheck.py <run1-dir>   (contains unit/, cluster/, diag/)"""
import sys, os, re, glob, json, bisect
MiB = 1024 * 1024; KiB = 1024
R = sys.argv[1]; bad = []
def ok(name, cond, detail=''):
    print('CHECK', 'OK ' if cond else 'BAD', name, detail)
    if not cond: bad.append(name)
# ---------------- unit ----------------
U = os.path.join(R, 'unit')
raw = open(os.path.join(U, 'obs.txt')).read().splitlines()
ok('unit: no FAILED in session.log', 'FAILED' not in open(os.path.join(U, 'session.log')).read())
ok('unit: stdout.log has no exception/ERROR line other than the control\'s designed IllegalArgumentException', not [l for l in open(os.path.join(U, 'stdout.log')).read().splitlines() if re.search(r'Exception|^ERROR| ERROR ', l) and 'control=huge-entry' not in l], '3 designed IAE lines in obs, none else')
pts = {}
for l in raw:
    m = re.match(r'OBS C=(\d+)MiB S=(\d+) rep=(\d+) phase=(\w+) (.*)', l)
    if m:
        nums = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)\b', m[5])}
        pts[(int(m[1]), int(m[2]), int(m[3]), m[4])] = nums
ok('unit: 27 points x 4 phases present', len(pts) == 108, str(len(pts)))
wmax = max(pts[k]['weighted'] / (k[0] * MiB) for k in pts if k[3] in ('fill', 'setCapacityHalf') and k[3] == 'fill')
ok('unit: fill weighted/C <= 1 at all 27 points', all(pts[k]['weighted'] <= k[0] * MiB for k in pts if k[3] == 'fill'), 'max ratio %.5f' % wmax)
ok('unit: concurrent maxWeighted <= C at all 27 points (sampled 10 ms)', all(pts[k]['maxWeighted'] <= k[0] * MiB for k in pts if k[3] == 'concurrent'))
ok('unit: finalWeighted <= C after threads joined', all(pts[k]['finalWeighted'] <= k[0] * MiB for k in pts if k[3] == 'concurrent'))
ok('unit: setCapacity(C/2) -> weighted <= C/2', all(pts[k]['weighted'] <= k[0] * MiB // 2 for k in pts if k[3] == 'setCapacityHalf'))
fillover = [(k, pts[k]['rssAnonDelta'] / MiB) for k in pts if k[3] == 'fill' and not ((0.8 if k[0] == 16 else 0.9) * k[0] * MiB <= pts[k]['rssAnonDelta'] <= k[0] * MiB + (48 if k[0] == 16 else 64) * MiB)]
print('INFO fill-phase RssAnon delta outside B2f range:', fillover)
ratio = sorted(pts[k]['peakRssDelta'] / (k[0] * MiB) for k in pts if k[3] == 'concurrent')
print('INFO concurrent peak RssAnon delta / C: min %.2f median %.2f max %.2f' % (ratio[0], ratio[len(ratio) // 2], ratio[-1]))
c = [l for l in raw if l.startswith('OBS clear')]
f2 = [int(re.search(r'peakRssDelta=(\d+)', l)[1]) for l in c if 'phase=fill2' in l]
ac = [re.search(r'weighted=(\d+) size=(\d+)', l).groups() for l in c if 'phase=afterClear' in l]
ok('unit: clear arm 3 reps, weighted==0 && size==0 after clear', len(f2) == 3 and all(x == ('0', '0') for x in ac))
print('INFO clear arm fill2 peak / C:', [round(x / (64 * MiB), 2) for x in f2])
ctl = [l for l in raw if l.startswith('OBS control=')]
ok('unit: controls (3 reps x 4 lines)', len(ctl) == 12 and sum('size=4 weighted=4' in l for l in ctl) == 6 and sum('IllegalArgumentException' in l for l in ctl) == 3 and sum('zero-capacity' in l and 'size=0' in l for l in ctl) == 3)
D = os.path.join(R, 'diag', 'diag.txt')
if os.path.exists(D):
    for l in open(D):
        if l.startswith('DIAG'):
            kv = dict(re.findall(r'(\w+)=(\S+)', l)); t = re.match(r'DIAG (C=\S+ S=\d+ threads=\d+)', l)[1]
            print('INFO diag %s arena=%s maxEntryBytes/C=%.2f rssBeforeTrim/C=%.2f rssAfterTrim/C=%.2f' % (t, kv['arenaMax'], int(kv['maxEntryBytes']) / int(kv['cap']), int(kv['rssDeltaBeforeTrim']) / int(kv['cap']), int(kv['rssDeltaAfterTrim']) / int(kv['cap'])))
# ---------------- cluster ----------------
K = os.path.join(R, 'cluster')
cap = {'c0': 0, 'c128': 128, 'c512': 512, 'c1024': 1024, 'n128': 128, 'c128b': 128}
est_rows = {}
for arm in cap:
    d = os.path.join(K, arm)
    if not os.path.isdir(d): print('INFO no arm', arm); continue
    y = open(os.path.join(K, 'cassandra.yaml.' + arm)).read()
    ok('%s: yaml row_cache_size=%dMiB once, provider SerializingCacheProvider' % (arm, cap[arm]), len(re.findall(r'^row_cache_size:', y, re.M)) == 1 and re.search(r'^row_cache_size: %dMiB$' % cap[arm], y, re.M) is not None and 'SerializingCacheProvider' in y)
    seg = open(os.path.join(d, 'system.log.segment'), errors='replace').read()
    ok('%s: startup log says capacity %d MiBs' % (arm, cap[arm]), ('Initializing row cache with capacity of %d MiBs' % cap[arm]) in seg)
    errs = [l for l in seg.splitlines() if l.startswith('ERROR')]
    ok('%s: no ERROR lines in system.log segment' % arm, not errs, str(errs[:2]))
    jr = [l.split(',') for l in open(os.path.join(d, 'jmx.csv')).read().splitlines()[1:]]
    ok('%s: JMX poll has no ERR line' % arm, all(r[0] != 'ERR' for r in jr))
    jr = [tuple(map(int, r)) for r in jr if r[0] != 'ERR']
    ok('%s: every polled sample Size <= Capacity' % arm, all(s <= c for _, s, c, _ in jr), 'n=%d max Size/MiB=%.2f' % (len(jr), max(s for _, s, _, _ in jr) / MiB))
    rss = [tuple(map(int, l.split(','))) for l in open(os.path.join(d, 'rss.csv')).read().splitlines()[1:]]
    ts = [r[0] for r in rss]
    cks = [json.loads(l) for l in open(os.path.join(d, 'ckpt.jsonl'))]
    for ck in cks:
        i = max([j for j in range(len(rss)) if rss[j][0] <= ck['epoch_ms']] or [0])   # last sample at or before the checkpoint (a client may start right after it)
        ok('%s %s: ckpt RssAnon matches the last 5 s sample at or before it (+-60 MiB)' % (arm, ck['name']), abs(rss[i][1] - ck['RssAnon_kb']) < 60 * KiB, 'ckpt %.0f MiB sample %.0f MiB dt %.1fs' % (ck['RssAnon_kb'] / KiB, rss[i][1] / KiB, (rss[i][0] - ck['epoch_ms']) / 1000))
        t = open(os.path.join(d, 'nmt-%s.txt' % ck['name'])).read()
        m = re.search(r'^Total: reserved=\d+KB, committed=(\d+)KB', t, re.M)
        ok('%s %s: NMT total re-parsed equals ckpt' % (arm, ck['name']), m and int(m[1]) == ck['nmt_total_committed_kb'])
    byname = {c['name']: c for c in cks}
    est_rows[arm] = byname
    if cap[arm] and arm != 'n128':
        r = byname['rand']
        hist = open(os.path.join(d, 'class_histogram.top.txt')).read()
        m = re.search(r'RefCountedMemory\s*$|^\s*\d+:\s+(\d+)\s+\d+\s+org.apache.cassandra.cache.RefCountedMemory', hist, re.M)
        cnt = int(re.search(r'^\s*\d+:\s+(\d+)\s+\d+\s+org\.apache\.cassandra\.cache\.RefCountedMemory', hist, re.M)[1]) if re.search(r'RefCountedMemory', hist) else 0
        ok('%s: RefCountedMemory instances (SerializingCache in use) ~ Entries at rand' % arm, cnt > 0 and abs(cnt - r['entries']) <= 0.02 * r['entries'] + 64, 'histogram %d JMX entries %d' % (cnt, r['entries']))
        ok('%s: Size/Capacity at rand' % arm, r['size'] <= r['capacity'], '%.4f' % (r['size'] / r['capacity']))
if 'c0' in est_rows:
    for arm in ('c128', 'c512', 'c1024', 'c128b'):
        if arm in est_rows:
            r = est_rows[arm]['rand']; b = est_rows['c0']['rand']
            # independent: median of RssAnon samples within +-30 s of the checkpoint, from rss.csv
            def med(a, t):
                rows = [x[1] for x in [tuple(map(int, l.split(','))) for l in open(os.path.join(K, a, 'rss.csv')).read().splitlines()[1:]] if abs(x[0] - t) <= 30000]
                rows.sort(); return rows[len(rows) // 2]
            e = (med(arm, r['epoch_ms']) - med('c0', b['epoch_ms'])) / KiB
            e2 = (r['RssAnon_kb'] - b['RssAnon_kb']) / KiB
            print('INFO %s est vs c0 at rand: ckpt-based %.1f MiB, rss.csv-median-based %.1f MiB, Size %.1f MiB (band [%.1f, %.1f])' % (arm, e2, e, r['size'] / MiB, 0.9 * r['size'] / MiB, (1.3 * r['size'] + 64 * MiB) / MiB))
T = os.path.join(K, 't1024', 'ckpt.jsonl')
if os.path.exists(T):   # post-hoc diagnostic arm
    r = {j['name']: j for j in map(json.loads, open(T))}
    g = lambda n: r[n]['RssAnon_kb'] / KiB
    print('INFO t1024 RssAnon MiB: idle %.0f rand %.0f trimfull %.0f set64 %.0f trimmed %.0f ; Size MiB at set64 %.1f' % (g('idle'), g('rand'), g('trimfull'), g('set64'), g('trimmed'), r['set64']['size'] / MiB))
    ok('t1024: Size fell to <=64 MiB on setcachecapacity 64 while RssAnon unchanged until malloc_trim', r['set64']['size'] <= 64 * MiB and abs(g('set64') - g('trimfull')) < 30 and g('trimmed') < g('set64') - 500, 'drop after trim %.0f MiB' % (g('set64') - g('trimmed')))
print('\nBAD CHECKS:', bad)
