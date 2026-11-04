#!/usr/bin/env python3
"""Independent self-check of run 1 of group-by-limit-incrementGroupCount-groupLimit--autonomous: re-parses the raw files with its own code (not
unit-analyze.py / cluster-analyze.py) and prints the numbers the conclusion cites, plus checks the analyzers did not rely on.
usage: selfcheck.py <run-dir>      (run-dir = ~/s4-b11-l79-logs/run1, holding unit/ and cluster/); writes <run-dir>/selfcheck.txt"""
import collections, datetime, glob, json, os, re, statistics, sys, xml.etree.ElementTree as ET

R = sys.argv[1]
out = []
def say(s):
    print(s); out.append(s)

# ---------------- unit ----------------
say('== UNIT (raw: unit/l79-unit.txt, unit/TEST-*.xml)')
root = ET.parse(glob.glob(R + '/unit/TEST-*.xml')[0]).getroot()
say(f'junit: tests={root.get("tests")} failures={root.get("failures")} errors={root.get("errors")}')
E = collections.defaultdict(list); W = {}; Cc = collections.defaultdict(list); start = {}
for line in open(R + '/unit/l79-unit.txt'):
    f = line.split()
    if len(f) < 2 or f[0] != 'L79':
        continue
    kv = dict(t.split('=', 1) for t in f[2:] if '=' in t)
    if f[1] == 'START':
        start = {k: int(v) for k, v in kv.items()}
    elif f[1] == 'E' and 'warm-up' not in line:
        E[(kv['ds'], int(kv['r']), int(kv['g']), int(kv['P']))].append(kv)
    elif f[1] == 'W':
        W[(kv['ds'], int(kv['r']), int(kv['g']), int(kv['P']))] = kv
    elif f[1] == 'C' and 'warm-up' not in line:
        Cc[int(kv['n'])].append(kv)
say(f'START {start}')
RS = sorted({k[1] for k in E if k[0] == 'S'}); GS = sorted({k[2] for k in E}); PS = sorted({k[3] for k in E})
ok = True
for r in RS:
    for P in PS:
        al, pk = {}, {}
        for g in GS:
            e = E[('S', r, g, P)]
            rows = {int(x['rows']) for x in e}; sub = {int(x['subpages']) for x in e}; grp = {int(x['groups']) for x in e}; mx = max(int(x['maxRowsPerSubpage']) for x in e)
            al[g] = statistics.mean(int(x['allocBytes']) for x in e); pk[g] = statistics.mean(int(x['peakPools']) for x in e)
            w = W[('S', r, g, P)]
            good = rows == {r} and grp == {1} and sub == {r // P + 1} and mx <= P
            if r > P:
                good = good and w['isDone'] == 'false' and w['groups'] == '0' and int(w['rowsCounted']) == P
            ok &= good
            say(f'S r={r} P={P} g={g}: rows={rows} groups={grp} subpages={sub} maxRows/sub={mx} whitebox(groups={w["groups"]},rowsCounted={w["rowsCounted"]},isDone={w["isDone"]}) alloc={int(al[g])} peakPools={int(pk[g])} {"ok" if good else "MISMATCH"}')
        say(f'  S r={r} P={P}: alloc max/min across g = {max(al.values()) / min(al.values()):.4f}; peakPools max/min = {max(pk.values()) / min(pk.values()):.3f}')
for P in PS:
    a = {}
    for g in GS:
        e = E[('M', start['mRows'], g, P)]
        rows = {int(x['rows']) for x in e}; grp = {int(x['groups']) for x in e}; w = W[('M', start['mRows'], g, P)]
        a[g] = statistics.mean(int(x['allocBytes']) for x in e)
        exp = start['mRows'] * min(g, start['mParts'])
        good = all(exp <= x <= exp + 1 for x in rows) and grp == {min(g, start['mParts'])}
        ok &= good
        say(f'M P={P} g={g}: rows={rows} groups={grp} whitebox(groups={w["groups"]},rowsCounted={w["rowsCounted"]},isDone={w["isDone"]}) alloc={int(a[g])} {"ok" if good else "MISMATCH"}')
for n in sorted(Cc):
    say(f'control n={n}: rows={sorted({int(x["rows"]) for x in Cc[n]})} alloc={statistics.mean(int(x["allocBytes"]) for x in Cc[n]):.0f} peakPools={statistics.mean(int(x["peakPools"]) for x in Cc[n]):.0f}')
ns = sorted(Cc)
say(f'control ratio alloc({ns[-1]})/alloc({ns[0]}) = {statistics.mean(int(x["allocBytes"]) for x in Cc[ns[-1]]) / statistics.mean(int(x["allocBytes"]) for x in Cc[ns[0]]):.1f}')
say(f'UNIT recomputation: {"all cells as predicted (rows, groups, sub-pages, white-box)" if ok else "MISMATCH found"}')

# ---------------- cluster ----------------
say('== CLUSTER (raw: cluster/cells.jsonl, l79.trace, heap.csv, gc.log, system.log)')
D = R + '/cluster'
cells = [json.loads(l) for l in open(D + '/cells.jsonl')]
trace = [(int(m[1]), int(m[2]), int(m[3]), m[4], m[5]) for m in (re.search(r'ms=(\d+) rows=(\d+) groups=(\d+) unfinished=(\w+) done=(\w+)', l) for l in open(D + '/l79.trace')) if m]
heap = [tuple(int(v) for v in l.split(',')) for l in open(D + '/heap.csv') if l.count(',') == 2]
gc = []
for l in open(D + '/gc.log', errors='replace'):
    m = re.search(r'\[(\d{4}-\d\d-\d\dT[\d:.]+)([+-]\d{4})\].*Pause (?:Young|Full|Remark|Cleanup)?.*?(\d+)M->(\d+)M\((\d+)M\)', l)
    if m:
        t = datetime.datetime.strptime(m[1] + m[2], '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
        gc.append((int(t), int(m[3]), int(m[4]), int(m[5])))
say(f'trace lines {len(trace)}, heap samples {len(heap)}, gc pauses parsed {len(gc)}, cells {len(cells)}')
ft = [c for c in cells if c['ds'] == 'FT'][0]
ftl = [t for t in trace if ft['t0'] <= t[0] <= ft['t1'] + 100]
K = len(ftl)
say(f'first-trigger query: K = {K} lines {ftl}')
wins = [(c['t0'], c['t1'] + 100) for c in cells if c['ds'] != 'idle']
unattr = [t for t in trace if t[0] >= ft['t0'] and not any(a <= t[0] <= b for a, b in wins)]
say(f'trace lines outside any query window after the first query: {len(unattr)}')
agg = collections.defaultdict(list)
for c in cells:
    if c['ds'] not in ('T', 'G') or c['warm']:
        continue
    w = [t for t in trace if c['t0'] <= t[0] <= c['t1'] + 100]
    pk = [u for ms, u, _ in heap if c['t0'] - 100 <= ms <= c['t1'] + 100]
    agg[(c['ds'], str(c['L']), c['P'])].append(dict(rows=sum(t[1] for t in w) / K, sub=len(w) / K, groups=sum(t[2] for t in w) / K, alloc=c['alloc_bytes'], rchar=c['rchar_delta'],
                                                   wall=c['wall_ms'], peak=max(pk), maxrows=max(t[1] for t in w), lastdone=all(t[4] == 'true' for t in w[-K:]),
                                                   nodone=not any(t[4] == 'true' for t in w[:-K]), ret=c['rows_returned'], err=c['error']))
for key in sorted(agg):
    v = agg[key]
    say(f'{key}: n={len(v)} rows={sorted({x["rows"] for x in v})} sub-pages={sorted({x["sub"] for x in v})} groups={sorted({x["groups"] for x in v})} maxrows/sub={max(x["maxrows"] for x in v)} '
        f'alloc_mean={statistics.mean(x["alloc"] for x in v):.0f} rchar_mean={statistics.mean(x["rchar"] for x in v):.0f} wall_mean={statistics.mean(x["wall"] for x in v):.0f}ms '
        f'peak_used_mean={statistics.mean(x["peak"] for x in v) / 1048576:.0f}MiB last_done={all(x["lastdone"] for x in v)} no_early_done={all(x["nodone"] for x in v)} '
        f'returned={sorted({x["ret"] for x in v})} errors={[x["err"] for x in v if x["err"]]}')
t_start = min(c['t0'] for c in cells if c['ds'] == 'T'); t_end = max(c['t1'] for c in cells)
pg = [(a, mx) for ms, b, a, mx in gc if t_start <= ms <= t_end]
if pg:
    say(f'after-GC occupancy during the query cells: max {max(a for a, _ in pg)}M of {pg[0][1]}M ({100 * max(a for a, _ in pg) / pg[0][1]:.0f} percent), pauses {len(pg)}')
sysl = open(D + '/system.log', errors='replace').read()
say(f'system.log: ERROR lines {len(re.findall(chr(10) + "ERROR", sysl))}, OutOfMemoryError {sysl.count("OutOfMemoryError")}')
cc = collections.defaultdict(list)
for c in cells:
    if c['ds'] == 'C' and not c['warm']:
        cc[c['L']].append((c['alloc_bytes'], c['rows_returned'], c['rchar_delta']))
for L in sorted(cc):
    say(f'control n={L}: rows={sorted({r for _, r, _ in cc[L]})} alloc_mean={statistics.mean(a for a, _, _ in cc[L]):.0f} rchar_mean={statistics.mean(x for _, _, x in cc[L]):.0f}')
open(R + '/selfcheck.txt', 'w').write('\n'.join(out) + '\n')
