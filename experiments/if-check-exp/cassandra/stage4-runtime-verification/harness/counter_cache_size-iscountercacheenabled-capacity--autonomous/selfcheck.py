#!/usr/bin/env python3
"""Independent re-derivation of the facts the three counter_cache_size conclusions rest on, by a route different from
analyze_*.py (unit lines split by token; cluster values re-read from session.log dictionaries, system.log.full init lines,
stress outputs and histograms re-parsed with a different parser). Usage: selfcheck.py <run1 dir>   -> prints OK/FAIL lines."""
import sys, os, re, ast, glob, json
R = sys.argv[1]; MiB = 1 << 20; bad = []
def ok(n, c, d=''):
    print('OK  ' if c else 'FAIL', n, d)
    if not c: bad.append(n)
def toks(l): return dict(t.split('=', 1) for t in l.split() if '=' in t)
# ---- unit
for lab in ('base', 'noguard'):
    L = open('%s/unit-%s/unit.txt' % (R, lab)).read().splitlines()
    ok('unit %s: ant exit 0' % lab, 'ant exit 0' in open('%s/unit-%s/session.log' % (R, lab)).read())
    ok('unit %s: 5 U1 arms, 5 U2 arms, 3 U3 arms' % lab, sum(l.startswith('U1 arm=') for l in L) == 5 and sum(l.startswith('U2 arm=') for l in L) == 5 and sum(l.startswith('U3 capMiB=') for l in L) == 3)
    for l in L:
        if l.startswith(('U1 arm', 'U2 arm', 'U3 capMiB')) and 'settled_weighted' in l:
            t = toks(l); w, c = int(t['settled_weighted']), int(t['settled_capacity'])
            ok('unit %s %s capMiB=%s weighted<=capacity' % (lab, l.split()[0], t.get('capMiB')), w <= c, '%d<=%d' % (w, c))
            if c == 0: ok('unit %s %s cap0 size==0' % (lab, l.split()[0]), t['settled_size'] == '0')
    helper0 = [toks(l)['helperCounter'] for l in L if l.startswith('U1 arm=') and toks(l)['capMiB'] == '0']
    ok('unit %s: helperCounter at capacity 0 == %s' % (lab, 'true' if lab == 'noguard' else 'false'), helper0 == [('true' if lab == 'noguard' else 'false')], str(helper0))
    rel = [toks(l) for l in L if l.startswith('U4 reload')]
    r0 = [t for t in rel if t['capMiB'] == '0']
    ok('unit %s: reload at 0 -> weighted 0; loadSavedReturned %s' % (lab, '>0' if lab == 'noguard' else '==0'), all(t['settled_weighted'] == '0' for t in r0) and all((int(t['loadSavedReturned']) > 0) == (lab == 'noguard') for t in r0), str([(t['loadSavedReturned'], t['settled_weighted']) for t in r0]))
    ok('unit %s: reload at 1,4 -> returned == saved keys and weighted<=cap' % lab, all(t['loadSavedReturned'] == '34952' and int(t['settled_weighted']) <= int(t['settled_capacity']) for t in rel if t['capMiB'] in ('1', '4')))
# ---- cluster
C = '%s/cluster' % R
_SESS = {}
def sessdicts(arm):
    """dictionaries logged by cluster-run.py in the one session.log, split by the '=== arm <label>' markers"""
    if not _SESS:
        cur = None
        for l in open('%s/session.log' % C):
            m = re.search(r'=== arm (\S+) ', l)
            if m: cur = m[1]; _SESS[cur] = []; continue
            m = re.search(r"(\{'t_ms'.*\})\s*$", l)
            if m and cur: _SESS[cur].append(ast.literal_eval(m[1]))
    return _SESS[arm]
def histbytes(f):
    cls = {}
    for l in open(f):
        p = l.split()
        if len(p) == 4 and p[0].endswith(':'): cls[p[3]] = (int(p[1]), int(p[2]))
    return cls
EXP = {'c0': 0, 'c1': 1 * MiB, 'c8': 8 * MiB, 'c64': 64 * MiB, 'cdef': 50 * MiB, 'c8b': 8 * MiB}
ent = {}
for a, cap in EXP.items():
    if not os.path.isdir('%s/%s' % (C, a)): continue
    D = sessdicts(a)
    ok('cluster %s: init log names the knob' % a, ('capacity of %d MiBs' % (cap // MiB)) in open('%s/%s/system.log.full' % (C, a)).read(), '')
    res = glob.glob('%s/%s/stress-pass*.results' % (C, a))
    ok('cluster %s: 2 stress passes, each 0 errors' % a, len(res) == 2 and all(re.search(r'Total errors\s*:\s*0\b', open(f).read()) for f in res))
    ok('cluster %s: Size<=Capacity in every session.log sample (%d)' % (a, len(D)), all(d['size'] <= d['capacity'] == cap for d in D))
    e1 = [d for d in D if d['phase'] == 'end-pass1'][-1]; e2 = [d for d in D if d['phase'] == 'end-pass2'][-1]
    ent[a] = e2['entries']
    if cap:
        ok('cluster %s: entries*120 == size (+-240) at end-pass2' % a, abs(e2['entries'] * 120 - e2['size']) <= 240, '%d*120 vs %d' % (e2['entries'], e2['size']))
        h = histbytes('%s/%s/hist-end-pass2.txt' % (C, a))
        ok('cluster %s: histogram CounterCacheKey instances == entries' % a, abs(h['org.apache.cassandra.cache.CounterCacheKey'][0] - e2['entries']) <= 0.01 * e2['entries'] + 2, str(h['org.apache.cassandra.cache.CounterCacheKey']))
    else:
        ok('cluster %s: zero entries in all samples' % a, all(d['entries'] == 0 and d['size'] == 0 for d in D))
        ok('cluster %s: no CounterCacheKey in any histogram' % a, all('org.apache.cassandra.cache.CounterCacheKey' not in histbytes(f) for f in glob.glob('%s/%s/hist-*.txt' % (C, a))))
    j = json.load(open('%s/%s/summary.json' % (C, a)))['jmx_final']
    ok('cluster %s: final JMX size<=capacity, entries match last sample' % a, j['size'] <= j['capacity'] and j['entries'] == e2['entries'], str(j))
    ok('cluster %s: no ERROR lines in system.log' % a, json.load(open('%s/%s/summary.json' % (C, a)))['errors_in_log'] == '0')
if 'c1' in ent and 'c8' in ent: ok('cluster entries 8 MiB / 1 MiB in [7.2,8.8]', 7.2 <= ent['c8'] / ent['c1'] <= 8.8, '%.3f' % (ent['c8'] / ent['c1']))
for a in ('rl0', 'rl1', 'rl8'):
    if not os.path.isdir('%s/%s' % (C, a)): continue
    D = sessdicts(a); cap = {'rl0': 0, 'rl1': MiB, 'rl8': 8 * MiB}[a]
    ok('cluster %s: capacity %d, size<=cap, no writes (requests 0)' % (a, cap), all(d['capacity'] == cap and d['size'] <= cap and d['requests'] == 0 for d in D), 'n=%d last=%s' % (len(D), D[-1]))
    ok('cluster %s: saved file present before start' % a, 'CounterCache' in open('%s/%s/saved_caches.ls' % (C, a)).read())
if os.path.isdir('%s/r8' % C):
    D = sessdicts('r8'); ok('cluster r8: entries 0 throughout', all(d['entries'] == 0 for d in D), 'n=%d' % len(D))
    ok('cluster r8: stress wrote the regular table (0 errors)', re.search(r'Total errors\s*:\s*0\b', open('%s/r8/stress-regular.results' % C).read()) is not None)
print('\nselfcheck FAILS: %d %s' % (len(bad), bad))
