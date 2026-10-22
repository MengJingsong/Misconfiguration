#!/usr/bin/env python3
"""Analysis of the cluster tier of NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous (case file B3f/B3g with K1, K2a, K2b).
usage: python3 -I analyze.py [<cluster log dir>=~/stage4-logs/ncs/cluster]
Reads, per run V4 / V8 / V16 / V128 and node n4 / n6: bm-<n>.txt (made lines, dump counters), samples-<n>.csv (JMX), rss.txt,
the t-* phase files, <n>-logs/system.log, stress consoles, status.txt. Prints one table per node and the row evaluation of K2b.
Readings only; it does not decide anything the K2b table does not say."""
import csv, glob, os, re, statistics, sys

D = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/ncs/cluster')
MIB = 1 << 20
VALUES = [4, 8, 16, 128]


def t(run, name):
    p = f'{D}/{run}/t-{name}'
    return int(open(p).read().strip()) if os.path.exists(p) else None


def node(run, n):
    r = {}
    bm = open(f'{D}/{run}/bm-{n}.txt').read().splitlines() if os.path.exists(f'{D}/{run}/bm-{n}.txt') else []
    made = [l for l in bm if l.startswith('made ')]
    r['k'] = max([int(re.search(r'n=(\d+)', l).group(1)) for l in made], default=0)
    r['made_ms'] = [int(re.search(r'ms=(\d+)', l).group(1)) for l in made]
    dumps = []
    for l in bm:
        if l.startswith('dump '):
            dumps.append({k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', l)})
    r['dump_last'] = dumps[-1] if dumps else {}
    tb, tw, tew, tr, ter, tt = (t(run, x) for x in ('baseline', 'start-write', 'end-write', 'start-read', 'end-read', 'end-tail'))
    r['dump_baseline'] = next((d for d in dumps if d['ms'] >= tb), {}) if tb else {}
    rows = []
    with open(f'{D}/{run}/samples-{n}.csv') as f:
        for row in csv.reader(f):
            if row[0] == 't0_ms' or row[1] == 'ERR':
                continue
            rows.append([int(x) for x in row])
    r['n_samples'] = len(rows)
    r['n_err'] = sum(1 for l in open(f'{D}/{run}/samples-{n}.csv') if ',ERR,' in l)
    # columns: t0,t1,capacity,size,used,overflow,pooled_derived,hits,misses,direct_used,direct_count
    r['capacity'] = sorted({x[2] for x in rows})
    base = [x for x in rows if tb <= x[0] < tw]
    load = [x for x in rows if tw <= x[0] <= ter]
    idle = [x for x in rows if ter + 15000 <= x[0] <= tt]
    r['n_base'], r['n_load'], r['n_idle'] = len(base), len(load), len(idle)
    r['pooled_derived_max_all'] = max(x[6] for x in rows)
    r['pooled_derived_idle'] = sorted({x[6] for x in idle})
    r['overflow_min'] = min(x[5] for x in rows)
    r['overflow_max'] = max(x[5] for x in rows)
    r['overflow_idle'] = [x[5] for x in idle]
    r['overflow_base'] = [x[5] for x in base]
    r['overflow_neg_samples'] = sum(1 for x in rows if x[5] < 0)
    r['used_gt_size_when_ovf0'] = sum(1 for x in rows if x[5] == 0 and x[4] > x[3])
    r['size_max'] = max(x[3] for x in rows)
    r['misses_end'] = rows[-1][8]
    r['hits_end'] = rows[-1][7]
    r['direct_base'] = statistics.median(x[9] for x in base) if base else None
    r['direct_max'] = max(x[9] for x in rows)
    r['direct_max_load'] = max((x[9] for x in load), default=None)
    r['made_before_write'] = sum(1 for m in r['made_ms'] if m < tw)
    r['made_during_load'] = sum(1 for m in r['made_ms'] if tw <= m <= ter)
    r['made_first_ms_rel_write'] = [(m - tw) / 1000 for m in r['made_ms']]
    # RSS
    rss = []
    if os.path.exists(f'{D}/{run}/rss.txt'):
        for l in open(f'{D}/{run}/rss.txt'):
            p = l.split()
            try:
                rss.append(int(p[p.index(n) + 1]))
            except (ValueError, IndexError):
                pass
    r['rss_max_mib'] = round(max(rss) / 1024, 1) if rss else None
    sl = f'{D}/{run}/{n}-logs/system.log'
    txt = open(sl, errors='replace').read() if os.path.exists(sl) else ''
    r['maxmem_lines'] = txt.count('Maximum memory usage reached')
    r['error_lines'] = len(re.findall(r'^ERROR', txt, re.M))
    m = re.search(r'Global buffer pool limit is .* and (\S+) for networking', txt)
    r['limit_line'] = m.group(1) if m else None
    return r


def stress(run, phase):
    p = f'{D}/{run}/stress-{phase}-console.log'
    if not os.path.exists(p):
        return None
    s = open(p, errors='replace').read()
    def g(rx):
        m = re.search(rx, s)
        return m.group(1).replace(',', '') if m else None
    return {'partitions': g(r'Total partitions\s*:\s*([\d,]+)'), 'errors': g(r'Total errors\s*:\s*([\d,]+)'),
            'op_rate': g(r'Op rate\s*:\s*([\d,]+)'), 'time': g(r'Total operation time\s*:\s*(\S+)')}


res = {}
for v in VALUES:
    run = f'V{v}'
    if not os.path.exists(f'{D}/{run}/t-end-tail'):   # complete runs only
        continue
    res[v] = {'n4': node(run, 'n4'), 'n6': node(run, 'n6'), 'write': stress(run, 'write'), 'read': stress(run, 'read'),
              'ring2UN': len(re.findall(r'^UN  127\.0\.0\.[46] ', open(f'{D}/{run}/status.txt').read(), re.M)) == 2
              if os.path.exists(f'{D}/{run}/status.txt') else False}

print(f'# analyze.py over {D}\n')
for v, R in res.items():
    print(f'## V{v}  networking_cache_size = {v} MiB, cap = {(v // 8) * 8} MiB; ring 2 UN: {R["ring2UN"]}; write {R["write"]}; read {R["read"]}')
    for n in ('n4', 'n6'):
        r = R[n]
        d = r['dump_last']
        print(f'  {n}: Capacity {r["capacity"]}  limit line {r["limit_line"]}  k={r["k"]} P_exact={r["k"] * 8} MiB '
              f'(made before write {r["made_before_write"]}, during load {r["made_during_load"]}, at s rel. write {r["made_first_ms_rel_write"]})')
        print(f'      dump(last): refuse={d.get("refuse")} gtrue={d.get("gtrue")} gfalse={d.get("gfalse")} gtiny={d.get("gtiny")} ovftrim={d.get("ovftrim")}'
              f'   dump(at baseline): {dict((k, x) for k, x in r["dump_baseline"].items() if k != "ms")}')
        print(f'      samples {r["n_samples"]} (ERR {r["n_err"]}; base {r["n_base"]}, load {r["n_load"]}, idle-tail {r["n_idle"]}); '
              f'pooled_derived max(all) {r["pooled_derived_max_all"]} idle {r["pooled_derived_idle"]}')
        print(f'      OverflowSize min {r["overflow_min"]} max {r["overflow_max"]} neg-samples {r["overflow_neg_samples"]} '
              f'baseline {r["overflow_base"][:3]}.. idle {r["overflow_idle"]}')
        print(f'      UsedSize>Size while overflow=0: {r["used_gt_size_when_ovf0"]}; Size max {r["size_max"]}; hits {r["hits_end"]} misses {r["misses_end"]}')
        db = r['direct_base']
        print(f'      direct MemoryUsed baseline {db} max {r["direct_max"]} (max-base {None if db is None else r["direct_max"] - db}, '
              f'= {None if db is None else round((r["direct_max"] - db) / MIB, 2)} MiB); made during load x 8 MiB = {r["made_during_load"] * 8} MiB; '
              f'RSS max {r["rss_max_mib"]} MiB')
        print(f'      "Maximum memory usage reached" lines {r["maxmem_lines"]}; ^ERROR lines {r["error_lines"]}')
    print()

# K2b evaluation
print('## K2b rows')
def cap(v): return (v // 8) * 8 * MIB
nodes = ('n4', 'n6')
def P(v, n): return res[v][n]['k'] * 8 * MIB
row2 = [(v, n) for v in res for n in nodes if P(v, n) > cap(v) or any(p > cap(v) + MIB for p in res[v][n]['pooled_derived_idle'])]
row3 = [(v, n) for v in res for n in nodes if any(p <= P(v, n) - 8 * MIB for p in res[v][n]['pooled_derived_idle'])]
def errfrac(v):
    out = []
    for ph in ('write', 'read'):
        s = res[v][ph]
        if s and s['errors'] is not None and s['partitions']:
            out.append(int(s['errors']) / max(1, int(s['partitions'])))
        else:
            out.append(None)
    return out
row8 = [v for v in res if any(res[v][n]['capacity'] != [v * MIB] for n in nodes) or not res[v]['ring2UN']
        or any(e is None or e > 0.01 for e in errfrac(v))]
row5 = 4 in res and (any(res[4][n]['k'] > 0 for n in nodes) or all(res[4][n]['dump_last'].get('refuse', 0) == 0 for n in nodes))
bind = [(v, n) for v in (8, 16) if v in res for n in nodes if P(v, n) == cap(v) and res[v][n]['dump_last'].get('refuse', 0) > 0]
row4 = not bind
row6 = all(res[v][n]['dump_last'].get('gfalse', 0) == 0 for v in res if v >= 8 for n in nodes)
gfalse_all = all(res[v][n]['dump_last'].get('gfalse', 0) > 0 for v in res if v >= 8 for n in nodes)
row1 = (not row2 and not row3 and not row8 and not row5 and not row4 and gfalse_all
        and all(res[4][n]['k'] == 0 and res[4][n]['dump_last'].get('refuse', 0) > 0 for n in nodes))
row7 = 4 in res and all(res[4][n]['overflow_neg_samples'] == 0 for n in nodes)
drift = 4 in res and any(res[4][n]['overflow_neg_samples'] > 0 for n in nodes)
print(f'row 2 (Refuted, P > cap): {row2 or "no"}')
print(f'row 3 (Refuted as traced, slab released): {row3 or "no"}')
print(f'row 8 (Invalid run): {row8 or "no"}   error fractions: {dict((v, errfrac(v)) for v in res)}')
print(f'row 5 (positive control failed): {row5}')
print(f'row 4 (cap never reached where the check runs): {row4}   binding (value, node): {bind}')
print(f'row 6 (gfalse = 0 in every run >= 8MiB): {row6}   gfalse > 0 in every run >= 8MiB: {gfalse_all}')
print(f'row 1 (Confirmed): {row1}')
print(f'row 7 (drift not shown at 4MiB): {row7}   last row (OverflowSize < 0 at 4MiB): {drift}')
print('\n## K2a / B3f sub-predictions')
for n in nodes:
    ks = [res[v][n]['k'] for v in res]
    print(f'  {n}: k per value {dict((v, res[v][n]["k"]) for v in res)}; order non-decreasing: {ks == sorted(ks)}')
for v in res:
    for n in nodes:
        r = res[v][n]
        okidle = all(abs(p - P(v, n)) <= 65536 for p in r['pooled_derived_idle'])
        print(f'  V{v} {n}: idle derived pooled == P_exact within 64 KiB: {okidle}; Capacity == NCS: {r["capacity"] == [v * MIB]}; '
              f'direct max-base >= pooled made during load: {None if r["direct_base"] is None else r["direct_max"] - r["direct_base"] >= r["made_during_load"] * 8 * MIB}')
