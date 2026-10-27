#!/usr/bin/env python3
"""Independent re-parse of run 1's raw files (stage-4 self-check). Does not import or call analyze_*.py.
Usage: selfcheck.py <run-logs-dir>      (<dir>/unit/ant.log, <dir>/unit/raw/unit.txt, <dir>/cluster/<arm>/..., <dir>/cluster/session.log)
Sources differing from the analyzers' inputs: unit = the 'STAGE4 key=value' echo lines in ant.log compared with unit.txt, and rules re-derived here from the
frozen B2f text; cluster = CKPT lines in session.log, every 5-second jmx.csv poll, the `nodetool info` Row Cache line (entries, size, hits, requests), rss.csv,
and system.log segments. Prints PASS/FAIL lines."""
import sys, os, re, json, csv
D = sys.argv[1]; fails = 0
def out(ok, what, got=''):
    global fails
    if not ok: fails += 1
    print('%s %s %s' % ('PASS' if ok else 'FAIL', what, got))
# ---------------- unit
ant = open(os.path.join(D, 'unit/ant.log'), errors='replace').read()
echo = {}
for m in re.finditer(r'STAGE4 ([A-Za-z0-9_.]+)=(\S*)', ant): echo[m.group(1)] = m.group(2)
raw = {}
for l in open(os.path.join(D, 'unit/raw/unit.txt')):
    if '=' in l: k, v = l.strip().split('=', 1); raw[k] = v
out(echo == raw, 'unit: ant.log echo lines equal unit.txt', '(%d keys vs %d)' % (len(echo), len(raw)))
out(re.search(r'Tests run: 1, Failures: 0, Errors: 0', ant) is not None, 'unit: ant reports the test passed')
g = lambda k: int(echo[k]) if k in echo and re.fullmatch(r'-?\d+', echo[k]) else None
LIM = [1, 4, 5, 6, 49, 50, 51, 1000]
for p, N, rc in (('5', 5, 5), ('50', 50, 50), ('ALL', 10 ** 9, 200)):
    out(g(p + '.populate.rowCount') == rc and g(p + '.populate.cachedLiveRows') == rc and g(p + '.after.rowCount') == rc, 'unit: arm %s stores %d rows (live = stored), before and after the L reads' % (p, rc), (g(p + '.populate.rowCount'), g(p + '.populate.cachedLiveRows'), g(p + '.after.rowCount')))
    # re-derived rule: covered(L) iff L <= min(N, rows) when the partition has more rows than N, else always; read counted as hit iff covered
    for L in LIM:
        cov = (N >= 200) or L <= N
        k = '%s.L%d.' % (p, L)
        out(echo.get(k + 'covered') == str(cov).lower() and g(k + 'dHit') == (1 if cov else 0) and g(k + 'dOut') == (0 if cov else 1) and g(k + 'dMiss') == 0,
            'unit: arm %s L=%d covered=%s <=> hit=%d out=%d' % (p, L, cov, 1 if cov else 0, 0 if cov else 1), (echo.get(k + 'covered'), g(k + 'dHit'), g(k + 'dOut')))
        he = L <= min(N, 200)
        out(echo.get(k + 'hasEnough') == str(he).lower(), 'unit: arm %s hasEnoughLiveData(L=%d) = %s' % (p, L, he), echo.get(k + 'hasEnough'))
    out(all(g('%s.populate.%s' % (p, f)) == g('%s.after.%s' % (p, f)) for f in ('serializedSize', 'rcSize', 'rcWeightedSize')), 'unit: arm %s serializedSize, size() and weightedSize() equal before and after the L reads' % p)
out(echo.get('NONE.populate.entry') == 'absent' and g('NONE.populate.hit') == 0 and g('NONE.populate.miss') == 0 and g('NONE.populate.outOfRange') == 0, 'unit: NONE leaves no entry and no counter moves')
ss = [g(p + '.populate.serializedSize') for p in ('5', '50', 'ALL')]
out(None not in ss and ss[0] < ss[1] < ss[2] and 7 <= ss[1] / ss[0] <= 10.5, 'unit: serialized size grows with N; size(50)/size(5) in 7..10.5', ss)
out(g('TTL.populate.rowsWithNonExpiringCells') == 0 and echo.get('TTL.L5.hasEnough') == 'true' and echo.get('TTL.L6.hasEnough') == 'false', 'unit: TTL variant takes the re-count branch (0 non-expiring rows; L=5 true, L=6 false)')
out(g('TOMB.populate.cachedLiveRows') == 5 and g('TOMB.populate.rowCount') == 55 and echo.get('TOMB.L6.hasEnough') == 'false', 'unit: TOMB stores 55 rows for 5 live; L=6 false after re-count', (g('TOMB.populate.rowCount'),))
out(g('NOCK.rowCount') == 1 and g('NOCK.cachedLiveRows') == 1, 'unit: NOCK stores its one row')
# ---------------- cluster
C = os.path.join(D, 'cluster'); sess = open(os.path.join(C, 'session.log'), errors='replace').read()
ARMS = ('n5', 'n50', 'nall', 'none', 't5'); ck = {}
for arm in ARMS:
    f = os.path.join(C, arm, 'ckpt.jsonl')
    if not os.path.exists(f): out(False, 'cluster: arm %s present' % arm); continue
    rows = {j['name']: j for j in map(json.loads, open(f))}; ck[arm] = rows
    logged = {json.loads(m.group(1))['epoch_ms'] for m in re.finditer(r'CKPT (\{.*\})', sess)}
    out(all(r['epoch_ms'] in logged for r in rows.values()), 'cluster %s: all %d checkpoints of ckpt.jsonl appear as CKPT lines in session.log' % (arm, len(rows)))
    jm = [r for r in csv.DictReader(open(os.path.join(C, arm, 'jmx.csv'))) if r['epoch_ms'].isdigit()]
    cap0 = rows['pass1']['capacity']
    out(len(jm) > 3 and max(int(r['size']) for r in jm) <= cap0, 'cluster %s: no jmx.csv poll above the 256 MiB capacity (max %d of %d, %d polls; includes the n50 shrink phase)' % (arm, max(int(r['size']) for r in jm), cap0, len(jm)))
    lastname = [k for k in ('pass3', 'pass2', 'pass1') if k in rows][0]; lastck = rows[lastname]
    nxt = [r for r in jm if int(r['epoch_ms']) <= lastck['epoch_ms'] + 1500]; lp = nxt[-1]
    out(int(lp['entries']) == lastck['entries'] and abs(int(lp['size']) - lastck['size']) <= 0.01 * max(lastck['size'], 1), 'cluster %s: last jmx.csv poll at/before checkpoint %s equals it' % (arm, lastname), (lp['entries'], lp['size'], lastck['entries'], lastck['size']))
    seg = open(os.path.join(C, arm, 'system.log.segment'), errors='replace').read()
    out(not [l for l in seg.splitlines() if l.startswith('ERROR')], 'cluster %s: no ERROR line in system.log segment' % arm)
    out(re.search(r'Initializing row cache with capacity of 256 MiBs', seg) is not None, 'cluster %s: node started with row cache 256 MiB' % arm)
    rs = [r for r in csv.DictReader(open(os.path.join(C, arm, 'rss.csv'))) if r['epoch_ms'].isdigit()]
    b = rows['baseline']; near = [r for r in rs if int(r['epoch_ms']) <= b['epoch_ms']][-1]
    out(abs(int(near['RssAnon_kb']) - b['RssAnon_kb']) < 20000, 'cluster %s: rss.csv agrees with the baseline RssAnon' % arm, (near['RssAnon_kb'], b['RssAnon_kb']))
    near = [r for r in rs if int(r['epoch_ms']) <= lastck['epoch_ms']][-1]
    out(abs(int(near['RssAnon_kb']) - lastck['RssAnon_kb']) < 40000, 'cluster %s: rss.csv sample before %s within 40 MB of that checkpoint' % (arm, lastname), (near['RssAnon_kb'], lastck['RssAnon_kb']))
# `nodetool info` Row Cache line (entries, size, hits, requests), once per arm, printed after the last pass and before the n50 shrink
infos = re.findall(r'Row Cache\s*: entries (\d+), size ([\d.]+) (\w+), capacity (\d+) MiB, (\d+) hits, (\d+) requests', sess)
armstarts = re.findall(r'=== arm (\w+) ', sess)
out(len(infos) == len(armstarts) == len(ARMS), 'cluster: one `nodetool info` Row Cache line per arm', (len(infos), len(armstarts)))
unit = {'bytes': 1, 'KiB': 1024, 'MiB': 1048576, 'GiB': 1073741824}
for arm, (en, sz, u, cp, hits, reqs) in zip(armstarts, infos):
    r = ck[arm]; last = r.get('pass3') or r['pass1']
    out(int(en) == last['entries'] and abs(float(sz) * unit[u] - last['size']) <= 0.01 * max(last['size'], 1) + 6000, 'cluster %s: nodetool info entries/size equals the gauges' % arm, (en, sz, u, last['entries'], last['size']))
    # the cache-level 'hits' is a lookup that found the key, so it counts the table's hits and its out-of-range hits (first version of this check compared with RowCacheHit alone and failed)
    out(int(hits) == last['hit'] + last['outOfRange'], 'cluster %s: nodetool info hits = RowCacheHit + RowCacheHitOutOfRange' % arm, (hits, last['hit'], last['outOfRange']))
    out(int(reqs) == last['hit'] + last['miss'] + last['outOfRange'], 'cluster %s: nodetool info requests = hit + miss + out of range' % arm, (reqs, last['hit'], last['miss'], last['outOfRange']))
# re-derived claims
def e(a, c='pass1'): return ck[a][c]['size'] / ck[a][c]['entries'] if a in ck and ck[a][c]['entries'] else None
out(e('n5') is not None and 600 <= e('n5') <= 1200 and ck['n5']['pass1']['entries'] == 20000, 'cluster: n5 holds 20,000 entries of 600..1200 B', e('n5'))
out(e('n50') is not None and 7 <= e('n50') / e('n5') <= 10.5 and ck['n50']['pass1']['entries'] == 20000, 'cluster: n50 holds 20,000 entries, e(50)/e(5) in 7..10.5', e('n50') / e('n5'))
out(e('nall') is not None and 3.3 <= e('nall') / e('n50') <= 4.1 and ck['nall']['pass1']['size'] >= 0.85 * 268435456 and 5000 <= ck['nall']['pass1']['entries'] <= 12000, 'cluster: nall e(ALL)/e(50) in 3.3..4.1, byte cap binds with 5,000..12,000 entries', (e('nall') / e('n50'), ck['nall']['pass1']['entries']))
for a in ('n5', 'n50'):
    s = [(ck[a][k]['size'], ck[a][k]['entries']) for k in ('pass1', 'pass2', 'pass3')]
    out(s[0] == s[1] == s[2], 'cluster: %s Size and Entries equal after P1, P2, P3' % a, s[0])
    c = [ck[a][k] for k in ('baseline', 'pass1', 'pass2', 'pass3')]
    out((c[1]['miss'] - c[0]['miss'], c[2]['outOfRange'] - c[1]['outOfRange'], c[2]['hit'] - c[1]['hit'], c[3]['hit'] - c[2]['hit']) == (20000, 20000, 0, 20000), 'cluster: %s counters P1 miss / P2 out of range / P2 hit / P3 hit = 20000 / 20000 / 0 / 20000' % a)
z = ck['none']['pass3']
out((z['entries'], z['size'], z['hit'], z['miss'], z['outOfRange']) == (0, 0, 0, 0, 0), 'cluster: NONE leaves the cache empty and the counters at 0')
out(ck['t5']['pass1']['entries'] == 2000 and e('t5') > e('n5') + 500, 'cluster: t5 stores 2,000 entries, each more than 500 B above the n5 entry', (e('t5'), e('n5')))
dn = ck['none']['pass3']['RssAnon_kb'] - ck['none']['baseline']['RssAnon_kb']
for a in ('n5', 'n50', 'nall'):
    d = ck[a]['pass3']['RssAnon_kb'] - ck[a]['baseline']['RssAnon_kb']; net = (d - dn) * 1024
    print('INFO %s RssAnon delta %.1f MB, net of none %.1f MB, Size %.1f MB, bound 1.5*Size+16MiB %.1f MB, refute line 1.5*Capacity %.1f MB' % (a, d * 1024 / 1e6, net / 1e6, ck[a]['pass3']['size'] / 1e6, (1.5 * ck[a]['pass3']['size'] + 16 * 1048576) / 1e6, 1.5 * 268435456 / 1e6))
    out(net <= 1.5 * 268435456, 'cluster: %s net RssAnon delta below 1.5 x Capacity (the B3g refute line)' % a)
for k in ('shrunk5s', 'shrunk60s', 'shrunk_p4'):
    if k in ck['n50']: print('INFO n50 %s: Size %d, Capacity %d, Entries %d' % (k, ck['n50'][k]['size'], ck['n50'][k]['capacity'], ck['n50'][k]['entries']))
print('SELFCHECK %s (%d FAIL)' % ('ALL PASS' if fails == 0 else 'FAILURES', fails))
sys.exit(1 if fails else 0)
