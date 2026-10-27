#!/usr/bin/env python3
"""Independent self-check of run 1 of group-limit-isdone-groupcounted--autonomous: re-parses the raw files with its own code (not
unit-analyze.py / cluster-analyze.py) and prints the numbers the conclusion cites, plus checks the analyzers did not rely on.
usage: selfcheck.py <run-dir>      (run-dir = ~/s4-b11-g72-logs/run1, holding unit/ and cluster/)"""
import collections, glob, json, os, re, statistics, sys, xml.etree.ElementTree as ET

R = sys.argv[1]
out = []
def say(s):
    print(s); out.append(s)

# ---------------- unit ----------------
say('== UNIT (raw: unit/g72-unit.txt, unit/TEST-*.xml)')
x = glob.glob(R + '/unit/TEST-*.xml')[0]
root = ET.parse(x).getroot()
say(f'junit: tests={root.get("tests")} failures={root.get("failures")} errors={root.get("errors")}')
E = collections.defaultdict(list); W = {}; Cc = collections.defaultdict(list)
for line in open(R + '/unit/g72-unit.txt'):
    f = line.split()
    if len(f) < 3 or f[0] != 'G72':
        continue
    kv = dict(t.split('=', 1) for t in f[2:] if '=' in t)
    if f[1] == 'E' and 'warm-up' not in line:
        E[(kv['ds'], kv['L'], int(kv['P']))].append(kv)
    elif f[1] == 'W':
        W[(kv['ds'], kv['L'], int(kv['P']))] = kv
    elif f[1] == 'C' and 'warm-up' not in line:
        Cc[int(kv['L'])].append(kv)
N = 20000
ok = True
for P in (100, 1000, 10000):
    al = {}
    for L in ('1', '1000', '100000', 'none'):
        e = E[('S', L, P)]
        rows = {int(r['rows']) for r in e}; sub = {int(r['subpages']) for r in e}; mx = max(int(r['maxRowsPerSubpage']) for r in e)
        al[L] = statistics.mean(int(r['allocBytes']) for r in e)
        w = W[('S', L, P)]
        good = rows == {N} and sub == {N // P + 1} and mx <= P and w['isDone'] == 'false' and w['groups'] == '0' and int(w['rowsCounted']) == P
        ok &= good
        say(f'S P={P} L={L}: rows={rows} subpages={sub} maxRowsPerSubpage={mx} whitebox(groups={w["groups"]},rowsCounted={w["rowsCounted"]},isDone={w["isDone"]}) alloc={int(al[L])} {"ok" if good else "MISMATCH"}')
    say(f'  S P={P}: alloc max/min across L = {max(al.values()) / min(al.values()):.4f}')
for P in (100, 1000, 10000):
    for L in ('1', '1000', '100000', 'none'):
        e = E[('M', L, P)]
        rows = {int(r['rows']) for r in e}; grp = {int(r['groups']) for r in e}; w = W[('M', L, P)]
        li = N + 1 if L in ('100000', 'none') else int(L)
        exp_rows = {N} if li > N else {int(L)}
        good = rows == exp_rows and grp == exp_rows
        ok &= good
        say(f'M P={P} L={L}: rows={rows} groups={grp} whitebox(groups={w["groups"]},rowsCounted={w["rowsCounted"]},isDone={w["isDone"]}) {"ok" if good else "MISMATCH"}')
for L in (100, 1000, 10000):
    say(f'control L={L}: rows={sorted({int(r["rows"]) for r in Cc[L]})} alloc={statistics.mean(int(r["allocBytes"]) for r in Cc[L]):.0f}')
say(f'control ratio alloc(10000)/alloc(100) = {statistics.mean(int(r["allocBytes"]) for r in Cc[10000]) / statistics.mean(int(r["allocBytes"]) for r in Cc[100]):.1f}')
say(f'UNIT recomputation: {"all cells as predicted" if ok else "MISMATCH found"}')

# ---------------- cluster ----------------
say('== CLUSTER (raw: cluster/cells.jsonl, g72.trace, heap.csv, gc.log, system.log, session.log)')
D = R + '/cluster'
cells = [json.loads(l) for l in open(D + '/cells.jsonl')]
trace = [(int(m[1]), int(m[2]), int(m[3]), m[4], m[5]) for m in (re.search(r'ms=(\d+) rows=(\d+) groups=(\d+) unfinished=(\w+) done=(\w+)', l) for l in open(D + '/g72.trace')) if m]
heap = [tuple(int(v) for v in l.split(',')) for l in open(D + '/heap.csv') if l.count(',') == 2]
# GC log: after-GC occupancy of pauses (live set plus floating garbage), with the node's uptime clock converted via the first line's wall clock
gc = []
for l in open(D + '/gc.log', errors='replace'):
    m = re.search(r'\[(\d{4}-\d\d-\d\dT[\d:.]+)([+-]\d{4})\].*Pause (?:Young|Full|Remark|Cleanup)?.*?(\d+)M->(\d+)M\((\d+)M\)', l)
    if m:
        import datetime
        t = datetime.datetime.strptime(m[1] + m[2], '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
        gc.append((int(t), int(m[3]), int(m[4]), int(m[5])))
say(f'trace lines {len(trace)}, heap samples {len(heap)}, gc pauses parsed {len(gc)}, cells {len(cells)}')
first = [c for c in cells if c['ds'] == 'G' and c['L'] == 1 and c['P'] == 100][0]
K = len([t for t in trace if first['t0'] <= t[0] <= first['t1'] + 100])
say(f'K (counters per sub-page, first-trigger query) = {K}')
# every trace line between the first-trigger query and the end must fall in a query window
wins = [(c['t0'], c['t1'] + 100) for c in cells if c['ds'] != 'idle']
unattr = [t for t in trace if t[0] >= first['t0'] and not any(a <= t[0] <= b for a, b in wins)]
say(f'trace lines outside any query window after the first query: {len(unattr)}')
agg = collections.defaultdict(list)
for c in cells:
    if c['ds'] not in ('S', 'G') or c['warm']:
        continue
    w = [t for t in trace if c['t0'] <= t[0] <= c['t1'] + 100]
    pk = [u for ms, u, _ in heap if c['t0'] - 100 <= ms <= c['t1'] + 100]
    gcs = [a for ms, b, a, mx in gc if c['t0'] <= ms <= c['t1'] + 100]
    agg[(c['ds'], str(c['L']), c['P'])].append(dict(rows=sum(t[1] for t in w) / K, sub=len(w) / K, groups=sum(t[2] for t in w) / K, alloc=c['alloc_bytes'], peak=max(pk),
                                                   postgc=max(gcs) if gcs else None, gcn=len(gcs), maxrows=max(t[1] for t in w), lastdone=all(t[4] == 'true' for t in w[-K:]),
                                                   nodone=not any(t[4] == 'true' for t in w[:-K]), ret=c['rows_returned'], err=c['error']))
for key in sorted(agg):
    v = agg[key]
    say(f'{key}: n={len(v)} rows={sorted({x["rows"] for x in v})} sub-pages={sorted({x["sub"] for x in v})} groups={sorted({x["groups"] for x in v})} maxrows/sub={max(x["maxrows"] for x in v)} '
        f'alloc_mean={statistics.mean(x["alloc"] for x in v):.0f} peak_used_mean={statistics.mean(x["peak"] for x in v) / 1048576:.0f}MiB '
        f'postGC_max={(max((x["postgc"] for x in v if x["postgc"] is not None), default=None))}M last_done={all(x["lastdone"] for x in v)} no_early_done={all(x["nodone"] for x in v)} '
        f'returned={sorted({x["ret"] for x in v})} errors={[x["err"] for x in v if x["err"]]}')
# after-GC occupancy over the whole query phase, and the B3g stop rule (heap above 90 percent for L=none)
t_start = min(c['t0'] for c in cells if c['ds'] == 'S'); t_end = max(c['t1'] for c in cells)
pg = [(a, mx) for ms, b, a, mx in gc if t_start <= ms <= t_end]
say(f'after-GC occupancy during the S/C/G cells: max {max(a for a, _ in pg)}M of {pg[0][1]}M ({100 * max(a for a, _ in pg) / pg[0][1]:.0f} percent), pauses {len(pg)}')
sysl = open(D + '/system.log', errors='replace').read()
say(f'system.log: ERROR lines {len(re.findall(chr(10) + "ERROR", sysl))}, OutOfMemory {sysl.count("OutOfMemory")}')
# control
for c in [c for c in cells if c['ds'] == 'C' and not c['warm']]:
    pass
cc = collections.defaultdict(list)
for c in cells:
    if c['ds'] == 'C' and not c['warm']:
        cc[c['L']].append((c['alloc_bytes'], c['rows_returned']))
for L in sorted(cc):
    say(f'control L={L}: rows={sorted({r for _, r in cc[L]})} alloc_mean={statistics.mean(a for a, _ in cc[L]):.0f}')
open(R + '/selfcheck.txt', 'w').write('\n'.join(out) + '\n')
