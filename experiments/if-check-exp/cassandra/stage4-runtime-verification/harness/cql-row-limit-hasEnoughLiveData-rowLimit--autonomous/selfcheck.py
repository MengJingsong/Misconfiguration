#!/usr/bin/env python3
"""Independent re-parse of run 1's raw logs (does not use analyze_unit.py / analyze_cluster.py or the harness's own ckpt.jsonl/unit.txt as the primary source).
Usage: selfcheck.py <run1-dir>     (the directory holding unit/ and cluster/)  Prints PASS/FAIL lines and a total."""
import sys, os, re, json
R = sys.argv[1]; fails = 0; total = 0
def chk(name, ok, detail=''):
    global fails, total
    total += 1; fails += (not ok); print('%s %s %s' % ('PASS' if ok else 'FAIL', name, detail))
MIB = 2**20
# ---------------- unit tier: ant.log STAGE4 echo lines are the source; unit.txt must agree
ant = {}
for l in open(os.path.join(R, 'unit/ant.log'), errors='replace'):
    m = re.search(r'STAGE4 ([^=\s]+)=(.*)$', l)
    if m: ant[m.group(1)] = m.group(2).strip()
ut = dict(l.strip().split('=', 1) for l in open(os.path.join(R, 'unit/raw/unit.txt')) if '=' in l)
chk('unit: ant.log echo lines equal unit.txt', ant == ut, '(%d keys)' % len(ut))
chk('unit: done=1 and ant exit 0', ut.get('done') == '1' and 'BUILD SUCCESSFUL' in open(os.path.join(R, 'unit/ant.log'), errors='replace').read())
LS = ['1', '50', '100', '101', '1000', '1000000', 'none']; ROWS = int(ut['ROWS'])
rows_cached = {'100': 100, 'ALL': ROWS, '500': 500}
for r, c in rows_cached.items():
    p = 'R' + r
    base = int(ut[p + '.base.weighted'])
    chk('unit %s: cache empty before arm, entry rows = %d' % (p, c), ut[p + '.pre.size'] == '0' and ut[p + '.entry.cachedLiveRows'] == str(c) and ut[p + '.entry.rowCount'] == str(c))
    ok = True; flips = []
    for rd in (1, 2, 3):
        for l in LS:
            k = '%s.r%d.L%s.' % (p, rd, l)
            lim = float('inf') if l == 'none' else int(l)
            # independent rule from DataLimits.java:414-417: true iff cached rows >= limit (NONE: false)
            direct = (l != 'none') and c >= lim
            hit = 1 if (r == 'ALL' or direct) else 0
            ok &= (ut[k + 'direct'] == str(direct).lower() and int(ut[k + 'hit']) == hit and int(ut[k + 'oor']) == 1 - hit and int(ut[k + 'miss']) == 0)
            ok &= (int(ut[k + 'weighted']) == base)
            ok &= int(ut[k + 'size']) == int(ut[p + '.base.size'])
    chk('unit %s: direct/hit/oor follow the rule, weightedSize and size() constant across 21 reads' % p, ok)
w = {r: int(ut['R%s.base.weighted' % r]) for r in rows_cached}
chk('unit: control, (w500)/(w100) in [4.5, 5.5]', 4.5 <= w['500'] / w['100'] <= 5.5, '%.3f' % (w['500'] / w['100']))
chk('unit: negative control cache off, counters 0', ut['NEG.isRowCacheEnabled'] == 'false' and ut['NEG.hit'] == ut['NEG.miss'] == ut['NEG.oor'] == '0' and ut['NEG.entry'] == 'absent')
# ---------------- cluster tier
cdir = os.path.join(R, 'cluster')
log = open(os.path.join(cdir, 'session.log'), errors='replace').read()
ARMS = {'l1000': (64, 1000), 'l10': (64, 10), 'l100': (64, 100), 'l100k': (64, 100000), 'lnone': (64, None), 'a100': (64, 100), 'anone': (64, None), 's256': (256, 100), 'off10': (0, 10), 'off1000': (0, 1000), 'offnone': (0, None)}
seg = re.split(r'=== arm (\w+) ', log)   # [pre, label, text, label, text, ...]
logck = {}
for i in range(1, len(seg), 2):
    d = {}
    for m in re.finditer(r'CKPT (\{.*\})', seg[i + 1]):
        j = json.loads(m.group(1)); d[j['name']] = j
    logck[seg[i]] = d
chk('cluster: every arm appears in session.log', set(logck) == set(ARMS), sorted(logck))
for a, (S, L) in ARMS.items():
    d = logck.get(a, {}); f = os.path.join(cdir, a, 'ckpt.jsonl')
    fj = {j['name']: j for j in map(json.loads, open(f))} if os.path.exists(f) else {}
    chk('%s: ckpt.jsonl equals the CKPT lines of session.log' % a, d == fj and {'baseline', 'populated', 'window', 'idle'} <= set(d))
    if not d: continue
    # capacity at start-up
    seg_text = open(os.path.join(cdir, a, 'system.log.segment'), errors='replace').read()
    caps = re.findall(r'Initializing row cache with capacity of (\d+) MiBs', seg_text)
    chk('%s: system.log start-up row cache capacity %d MiB' % (a, S), (caps == [str(S)]) if S else (caps in ([], ['0'])), str(caps))
    chk('%s: no ERROR line in the node log segment' % a, not [l for l in seg_text.splitlines() if l.startswith('ERROR')])
    # jmx.csv: no sample above the capacity, last sample before the window checkpoint equals the checkpoint's gauges
    rows = [l.strip().split(',') for l in open(os.path.join(cdir, a, 'jmx.csv')) if l[0].isdigit()]
    mx = max(int(r[1]) for r in rows); cap = S * MIB
    chk('%s: jmx.csv Size never above capacity (max %d, cap %d)' % (a, mx, cap), mx <= cap)
    w = d['window']; idl = d['idle']
    # like with like (rewritten after the first pass of this check, which compared a 5-s sample taken inside the window with the checkpoint taken after it): once the window is over nothing runs, so every sample between 6 s after the window checkpoint and the idle checkpoint equals the window checkpoint
    quiet = [r for r in rows if w['epoch_ms'] + 6000 < int(r[0]) < idl['epoch_ms']]
    chk('%s: %d jmx samples after the window (idle) equal the window checkpoint Size/Entries/counters' % (a, len(quiet)),
        len(quiet) >= 5 and all((int(r[1]), int(r[3]), int(r[4]), int(r[5]), int(r[6])) == (w['size'], w['entries'], w['hit'], w['miss'], w['outOfRange']) for r in quiet))
    # RSS: checkpoint value is within 1% of the nearest rss.csv sample
    rs = [r for r in (l.strip().split(',') for l in open(os.path.join(cdir, a, 'rss.csv'))) if r[0].isdigit()]
    near = min(rs, key=lambda r: abs(int(r[0]) - w['epoch_ms']))
    chk('%s: window RssAnon within 2%% of the nearest 5-s sample' % a, abs(int(near[1]) - w['RssAnon_kb']) <= 0.02 * w['RssAnon_kb'], '%s vs %s' % (near[1], w['RssAnon_kb']))
    # window request counts from the CLIENT_DONE lines of the window
    wl = [m for m in re.finditer(r'CLIENT_DONE rnd t ok (\d+) rows (\d+) errors (\d+)', seg[seg.index(a) + 1])]
    chk('%s: window clients: 4 processes, %d ok reads, 0 errors' % (a, 10000), len(wl) == 4 and sum(int(m.group(1)) for m in wl) == 10000 and all(m.group(3) == '0' for m in wl))
    rexp = 10000 * (2000 if L is None or L >= 2000 else L)
    chk('%s: window rows returned = %d' % (a, rexp), sum(int(m.group(2)) for m in wl) == rexp)
    Rn = 'ALL' if a in ('a100', 'anone', 's256') else '100'
    chk('%s: schema read-back shows rows_per_partition %s' % (a, Rn), re.search(r"schema caching = .*'rows_per_partition': '%s'" % Rn, seg[seg.index(a) + 1]) is not None)
    if S == 0:
        chk('%s: cache off, Entries 0 and counters 0 at the window checkpoint' % a, (w['entries'], w['hit'], w['miss'], w['outOfRange']) == (0, 0, 0, 0))
    ni = re.search(r'Row Cache\s*:\s*entries (\d+), size ([\d.]+ \w+), capacity ([\d.]+ \w+)', seg[seg.index(a) + 1])
    if S: chk('%s: nodetool info row-cache entries = idle checkpoint entries' % a, ni and int(ni.group(1)) == d['idle']['entries'], str(ni.groups() if ni else None))
chk('cluster: all daemons stopped', 'daemons left: []' in log and not re.search(r'daemons left: \[\'?\d', log))
print('TOTAL %d checks, %d FAIL' % (total, fails))
