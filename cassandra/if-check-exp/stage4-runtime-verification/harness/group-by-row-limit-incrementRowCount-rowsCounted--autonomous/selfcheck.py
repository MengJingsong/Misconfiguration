#!/usr/bin/env python3
"""Independent self-check (stage 4 step 4) of group-by-row-limit-incrementRowCount-rowsCounted--autonomous.
usage: selfcheck.py <run-dir>     (the dir that holds unit/ and cluster/ of one run, e.g. ~/s4-b11-b78-logs/run1)
Re-parses the raw files with code that does not share the analyzers' parsing: the junit XML (system-out) for the unit tier; cells.jsonl, the
Byteman traces, gc logs, heap samples and system logs for the cluster tier. Recomputes the numbers the conclusion cites and prints them.
Nothing here decides a verdict."""
import glob, json, os, re, sys, xml.etree.ElementTree as ET
from datetime import datetime

R = sys.argv[1]
MB = 1048576.0
print('== unit tier (ant.log = the probe\'s stdout, a second copy of the lines the text file holds)')
xmls = glob.glob(f'{R}/unit/TEST-*.xml')
for x in xmls:
    r = ET.parse(x).getroot()
    print('junit:', r.get('name'), 'tests', r.get('tests'), 'failures', r.get('failures'), 'errors', r.get('errors'))
lines = []
for l in open(f'{R}/unit/ant.log', errors='replace'):
    k = l.find(' - B78 ')
    if k >= 0:
        lines.append(l[k + 3:].strip())
print('B78 lines in ant.log:', len(lines))
fl = open(f'{R}/unit/b78-unit.txt').read().splitlines()
print('ant.log copy equals the text file:', sorted(lines) == sorted(l for l in fl if l.startswith('B78 ')))
E = [l for l in lines if l.startswith('B78 E ') and '(warm-up)' not in l]
for p in ('1', '7', '1000', '10000', 'unset'):
    rs = [l for l in E if l.startswith(f'B78 E p={p} ')]
    vals = [{k: v for k, v in re.findall(r'(\w+)=(\S+)', l)} for l in rs]
    print(f' p={p}: reps {len(rs)} rows {[v["rows"] for v in vals]} subpages {[v["subpages"] for v in vals]} max/subpage {[v["maxRowsPerSubpage"] for v in vals]} pages {[v["pages"] for v in vals]} alloc {[v["allocBytes"] for v in vals]}')
for l in lines:
    if l.startswith('B78 W ') or l.startswith('B78 CB '):
        d = dict(re.findall(r'(\w+)=(\S+)', l))
        p = d.get('p') or re.search(r' p=(\S+)', l).group(1)
        n = 10000 if p == 'unset' else int(p)
        print(f' {l.split()[1]} p={p}: firstReadBytes {d["firstReadBytes"]} per row {int(d["firstReadBytes"]) / n:.2f}' + (f' rowsCounted {d["rowsCounted"]} groups {d["groups"]} isDone {d["isDone"]}' if l.startswith('B78 W ') else ''))
for l in lines:
    if l.startswith('B78 C ') and '(warm-up)' not in l:
        print(' ', l[:150])

print('\n== cluster tier')
C = f'{R}/cluster'
if not os.path.isdir(C):
    sys.exit(0)
cells = [json.loads(l) for l in open(f'{C}/cells.jsonl')]
gcruns = [json.loads(l) for l in open(f'{C}/gcrun.jsonl')]


def trace(n):
    o = []
    for l in open(f'{C}/b78-n{n}.trace', errors='replace'):
        m = re.match(r'.*GB ms=(\d+) rows=(\d+) groups=(\d+) unfinished=(\w+) done=(\w+)', l)
        if m:
            o.append(tuple(int(m.group(i)) if i < 4 else m.group(i) for i in range(1, 6)))
    return o


tr = {1: trace(1), 2: trace(2)}
gcev = {1: [], 2: []}
for n in (1, 2):
    for fn in glob.glob(f'{C}/gc-n{n}.log*'):
        for l in open(fn, errors='replace'):
            m = re.match(r'\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)([+-]\d{4})\]\[[^\]]+\] GC\(\d+\) (Pause \S+).* (\d+)M->(\d+)M\(\d+M\) ([0-9.]+)ms', l)
            if m:
                ts = datetime.strptime(m.group(1) + m.group(2), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
                gcev[n].append((ts, m.group(3), int(m.group(4)), int(m.group(5)), float(m.group(6))))
cal = next(c for c in cells if c.get('label') == 'calibration')
K = sum(1 for n in (1, 2) for t in tr[n] if cal['t0'] - 500 <= t[0] <= cal['t1'] + 500)
print('K =', K)


def qres(c, glabel):
    t0, t1 = c['t0'], c['t1']
    r = dict(wall=c['wall_ms'], err=(c['error'] or '')[:70])
    w = [t for n in (1, 2) for t in tr[n] if t0 - 300 <= t[0] <= t1 + 300]
    r['subreads'] = len(w) / K
    r['rows'] = sum(t[1] for t in w) / K
    r['maxrows'] = max([t[1] for t in w] or [0])
    for n in (1, 2):
        g = [x for x in gcruns if x['label'] == glabel and x['node'] == n]
        base = None
        if g:
            fulls = [e for e in gcev[n] if g[-1]['t0'] - 1000 <= e[0] <= g[-1]['t1'] + 3000 and e[1].startswith('Pause')]
            fulls = [e for e in fulls if 'Full' in e[1] or e[3] <= e[2]]
            base = [e for e in gcev[n] if g[-1]['t0'] - 1000 <= e[0] <= g[-1]['t1'] + 3000 and e[1] == 'Pause' ]
        # a forced collection prints "Pause Full (System.gc())": the regex captured 'Pause' + first word, so match on the raw text again below
        r[f'n{n}'] = None
    return r


# second, independent baseline reader: the raw line text of Pause Full
def full_after(n, t0, t1):
    best = None
    for fn in glob.glob(f'{C}/gc-n{n}.log*'):
        for l in open(fn, errors='replace'):
            m = re.match(r'\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)([+-]\d{4})\].*Pause Full.* (\d+)M->(\d+)M', l)
            if m:
                ts = datetime.strptime(m.group(1) + m.group(2), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
                if t0 - 1000 <= ts <= t1 + 3000:
                    best = int(m.group(4))
    return best


def heap_samples(n):
    o = []
    for l in open(f'{C}/heap-n{n}.csv'):
        a = l.strip().split(',')
        if len(a) == 3 and a[0].isdigit():
            o.append((int(a[0]), int(a[1])))
    return o


hs = {1: heap_samples(1), 2: heap_samples(2)}
print('label fetch rep | wall ms | rows | sub-reads | max rows/line | n1 base | n1 peak-after | n1 delta | n2 delta | n1 pause frac | n1 used max | err')
prefix = {'groupby': 'gb', 'control-select': 'ctl', 'small-rows': 'small', 'guardrail': 'guardrail'}
for c in cells:
    lab = c.get('label')
    if lab not in prefix:
        continue
    gl = prefix[lab] + ('' if lab == 'guardrail' else f"-{c['fetch']}")
    r = qres(c, gl)
    cols = []
    for n in (1, 2):
        g = [x for x in gcruns if x['label'] == gl and x['node'] == n and x['t1'] <= c['t0']]
        base = full_after(n, g[-1]['t0'], g[-1]['t1']) if g else None
        ev = [e for e in gcev[n] if c['t0'] <= e[0] <= c['t1']]
        peak = max([e[3] for e in ev] or [None]) if ev else None
        pf = sum(e[4] for e in ev) / max(1, c['wall_ms'])
        um = max([u for ms, u in hs[n] if c['t0'] <= ms <= c['t1']] or [0]) / MB
        cols.append((base, peak, None if (base is None or peak is None) else peak - base, pf, um))
    print(f"{lab} {c['fetch']} {c['rep']} | {r['wall']} | {int(r['rows'])} | {int(r['subreads'])} | {r['maxrows']} | {cols[0][0]} | {cols[0][1]} | {cols[0][2]} | {cols[1][2]} | {cols[0][3]:.2f} | {cols[0][4]:.0f} | {r['err']} | dead {c.get('dead_nodes')}")
# OOM lines
for n in (1, 2):
    cnt = 0
    for l in open(f'{C}/system-n{n}.log', errors='replace'):
        if re.search(r'java\.lang\.OutOfMemoryError|OutOfMemoryError:', l) and '-XX' not in l:
            cnt += 1
    print(f'node {n}: OutOfMemoryError lines in system.log: {cnt}; ERROR lines: {sum(1 for l in open(f"{C}/system-n{n}.log", errors="replace") if l.startswith("ERROR"))}')
print('trace lines outside any timed window (n1, n2):', [sum(1 for t in tr[n] if not any(c['t0'] - 300 <= t[0] <= c['t1'] + 300 for c in cells if 't1' in c)) for n in (1, 2)])
