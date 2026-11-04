#!/usr/bin/env python3
"""Independent re-parse of run 1's raw files (stage-4 self-check). Does not import or call analyze_*.py.
Usage: selfcheck.py <run-logs-dir>      (<dir>/unit/ant.log, <dir>/unit/raw/unit.txt, <dir>/cluster/<arm>/..., <dir>/cluster/session.log)
Sources used instead of the analyzers' inputs: unit = the 'STAGE4 key=value' echo lines in ant.log (printed by the test to stdout) compared with unit.txt;
cluster = the CKPT lines in session.log, the last row of jmx.csv before each checkpoint, the 'Row Cache' line of `nodetool info` and rss.csv, plus system.log segments.
Prints PASS/FAIL lines."""
import sys, os, re, json, glob, csv
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
out(re.search(r'Tests run: 1, Failures: 0, Errors: 0', ant) is not None or re.search(r'\[junit\] Tests run: 1, Failures: 0', ant) is not None, 'unit: ant reports the test passed')
g = lambda k: int(echo[k]) if k in echo and re.fullmatch(r'-?\d+', echo[k]) else None
for n, e in (('1', 1), ('10', 10), ('100', 100), ('ALL', 1000), ('2000', 1000)):
    out(g('N%s.cachedLiveRows' % n) == e and g('N%s.rowCount' % n) == e, 'unit: N=%s holds %d rows (live = stored)' % (n, e), (g('N%s.cachedLiveRows' % n), g('N%s.rowCount' % n)))
out(all(g('N%s.cachedLiveRows' % n) <= int(n) for n in ('1', '10', '100')), 'unit: no N below 1000 stored more live rows than N')
out(echo.get('NNONE.entry') == 'absent', 'unit: NONE leaves no entry')
out(g('TOMBROWS.rowCount') == 60 and g('TOMBROWS.cachedLiveRows') == 10, 'unit: row-deletion variant 10 live, 60 stored', (g('TOMBROWS.cachedLiveRows'), g('TOMBROWS.rowCount')))
out(g('TOMBRANGE.rowCount') == 10 and (g('TOMBRANGE.rangeTombstones') or 0) >= 1, 'unit: range-tombstone arm 10 stored rows + range in deletionInfo', (g('TOMBRANGE.rowCount'), g('TOMBRANGE.rangeTombstones')))
out(echo.get('N10.coveredFullSlice') == 'false' and echo.get('NALL.coveredFullSlice') == 'true', 'unit: coverage test false at cachedLiveRows == N, true when partition has fewer than N rows')
s = [g('N%s.serializedSize' % n) for n in ('1', '10', '100', 'ALL')]
out(None not in s and s[0] < s[1] < s[2] < s[3] and 8 <= s[2] / s[1] <= 12, 'unit: serialized size grows with N; size(100)/size(10) in 8..12', s)
# ---------------- cluster
C = os.path.join(D, 'cluster'); sess = open(os.path.join(C, 'session.log'), errors='replace').read()
ck = {}
for arm in ('n1', 'n10', 'n100', 'nall', 't10', 'none', 'c32'):
    f = os.path.join(C, arm, 'ckpt.jsonl')
    if not os.path.exists(f): out(False, 'cluster: arm %s present' % arm); continue
    rows = {j['name']: j for j in map(json.loads, open(f))}; ck[arm] = rows
    # 1. ckpt.jsonl agrees with the CKPT lines printed in session.log
    logged = [json.loads(m.group(1)) for m in re.finditer(r'CKPT (\{.*\})', sess) if json.loads(m.group(1)).get('epoch_ms') in {r['epoch_ms'] for r in rows.values()}]
    out(len(logged) == len(rows), 'cluster %s: %d checkpoints in ckpt.jsonl match CKPT lines in session.log' % (arm, len(rows)))
    # 2. the 5-second JMX poll (independent sampling of the same gauges): at no sampled instant does Size exceed Capacity, and the last poll (steady state,
    #    after the last pass and its idle time) equals the last checkpoint within 1%
    jm = [r for r in csv.DictReader(open(os.path.join(C, arm, 'jmx.csv'))) if r['epoch_ms'].isdigit()]
    capb = rows['pass1']['capacity']
    out(len(jm) > 3 and max(int(r['size']) for r in jm) <= capb, 'cluster %s: no jmx.csv poll above the capacity (max %d of %d, %d polls)' % (arm, max(int(r['size']) for r in jm), capb, len(jm)))
    lastck = rows.get('pass2') or rows['pass1']; lastp = jm[-1]
    out(abs(int(lastp['entries']) - lastck['entries']) <= 0.01 * max(lastck['entries'], 1) and abs(int(lastp['size']) - lastck['size']) <= 0.01 * max(lastck['size'], 1), 'cluster %s: last jmx.csv poll equals the last checkpoint (1%%)' % arm, (lastp['entries'], lastp['size'], lastck['entries'], lastck['size']))
    # 3. system.log segment has no ERROR line and logs the row cache capacity
    seg = open(os.path.join(C, arm, 'system.log.segment'), errors='replace').read()
    out(not [l for l in seg.splitlines() if l.startswith('ERROR')], 'cluster %s: no ERROR line in system.log segment' % arm)
    cap = rows['pass1']['capacity'] // 1048576
    out(re.search(r'Initializing row cache with capacity of %d MiBs' % cap, seg) is not None, 'cluster %s: node started with row cache %d MiB' % (arm, cap))
    # 4. rss.csv: the last sample at or before the baseline checkpoint is the baseline RssAnon (within 20 MB; sampled every 5 s, idle before the checkpoint)
    rs = [r for r in csv.DictReader(open(os.path.join(C, arm, 'rss.csv'))) if r['epoch_ms'].isdigit()]
    b = rows['baseline']; before = [r for r in rs if int(r['epoch_ms']) <= b['epoch_ms']]; near = before[-1]
    out(abs(int(near['RssAnon_kb']) - b['RssAnon_kb']) < 20000, 'cluster %s: rss.csv agrees with the baseline RssAnon' % arm, (near['RssAnon_kb'], b['RssAnon_kb']))
    lastck = rows.get('pass2') or rows['pass1']; lastr = rs[-1]
    out(abs(int(lastr['RssAnon_kb']) - lastck['RssAnon_kb']) < 40000, 'cluster %s: last rss.csv sample within 40 MB of the last checkpoint' % arm, (lastr['RssAnon_kb'], lastck['RssAnon_kb']))
# `nodetool info` Row Cache line vs pass-2 (or pass-1 for t10) gauges, taken from session.log in arm order
infos = re.findall(r'Row Cache\s*: entries (\d+), size ([\d.]+) (\w+), capacity (\d+) MiB', sess)
order = [a for a in ('n10', 'n1', 'n100', 'nall', 't10', 'none', 'c32') if a in ck]
armstarts = re.findall(r'=== arm (\w+) ', sess)
out(len(infos) == len(armstarts), 'cluster: one `nodetool info` Row Cache line per arm', (len(infos), len(armstarts)))
unit = {'bytes': 1, 'KiB': 1024, 'MiB': 1048576, 'GiB': 1073741824}
for arm, (en, sz, u, cp) in zip(armstarts, infos):
    last = ck[arm].get('pass2') or ck[arm]['pass1']
    approx = float(sz) * unit[u]
    out(int(en) == last['entries'] and abs(approx - last['size']) <= 0.01 * max(last['size'], 1) + 600, 'cluster %s: nodetool info entries/size equals the gauges' % arm, (en, sz, u, last['entries'], last['size']))
# re-derived claims
R = 1.05 * 1024
def e(a, c='pass1'): return ck[a][c]['size'] / ck[a][c]['entries'] if a in ck and ck[a][c]['entries'] else None
for a, N in (('n1', 1), ('n10', 10), ('n100', 100)):
    out(e(a) is not None and 0.75 <= e(a) / (N * R) <= 1.4, 'cluster: bytes/entry of %s within 0.75..1.4 of N x 1.05 KiB' % a, e(a) and round(e(a) / (N * R), 3))
out(e('nall') is not None and 250 * 1024 <= e('nall') <= 400 * 1024, 'cluster: bytes/entry of ALL in 250..400 KiB', e('nall'))
for a in ('n100', 'nall'): out(ck[a]['pass1']['size'] <= 256 * 1048576 and ck[a]['pass1']['entries'] < 10000, 'cluster: %s at or under 256 MiB with entries < 10000' % a, (ck[a]['pass1']['size'], ck[a]['pass1']['entries']))
out(ck['none']['pass2']['entries'] == 0 and ck['none']['pass2']['size'] == 0 and ck['none']['pass2']['hit'] == 0 and ck['none']['pass2']['miss'] == 0, 'cluster: NONE leaves the cache empty and counters at 0')
out(ck['c32']['pass1']['size'] <= 32 * 1048576 and 0 < ck['c32']['pass1']['entries'] < 10000, 'cluster: 32 MiB control fills (entries > 0) and stays under 32 MiB', (ck['c32']['pass1']['size'], ck['c32']['pass1']['entries']))
print('SELFCHECK %s (%d FAIL)' % ('ALL PASS' if fails == 0 else 'FAILURES', fails))
sys.exit(1 if fails else 0)
