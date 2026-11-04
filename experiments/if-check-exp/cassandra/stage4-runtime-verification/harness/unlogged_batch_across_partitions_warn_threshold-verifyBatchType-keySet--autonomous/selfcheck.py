#!/usr/bin/env python3
"""Independent self-check for unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous.
usage: selfcheck.py <run-dir>      (e.g. ~/s4-b9-bu-logs/run1 or the excerpt copy in results/<stem>/run1)
Re-derives the readings from raw files only (test.out, TEST-*.xml, per-arm system.log, heap.csv, dirsize.csv, tablestats.csv, load/probe lines in
summary.txt), not from results.json or the script's own EXPECTED lines, and prints one CHECK line per claim with the numbers."""
import glob, json, os, re, sys
d = sys.argv[1]
ok_all = True


def check(desc, cond, detail=''):
    global ok_all
    ok_all &= bool(cond)
    print(f'CHECK {"ok " if cond else "BAD"} {desc} {detail}')


# ---- unit tier
u = d + '/unit'
if os.path.isdir(u):
    t = open(u + '/test.out').read()
    x = glob.glob(u + '/TEST-*.xml')[0]
    xs = open(x).read()
    m = re.search(r'tests="(\d+)".*?failures="(\d+)"|errors="(\d+)" failures="(\d+)"', xs)
    check('unit: JUnit XML 1 test, 0 failures, 0 errors', re.search(r'errors="0"', xs) and re.search(r'failures="0"', xs) and 'tests="1"' in xs)
    rd = {}
    for l in t.splitlines():
        m = re.match(r'STAGE4 reading arm=(\S+) (\S+) client_warnings=(\d+) log_warns=(\d+) count=(\d+) memtable_live_bytes=(\d+)(?: error="(.*)")?', l)
        if m:
            rd[(m.group(1), m.group(2))] = tuple(int(m.group(i)) for i in range(3, 7)) + (m.group(7) or '',)
    for thr in (1, 10, 1000):
        a = rd[(f't{thr}', 'u50-first')]
        w = 1 if 50 > thr else 0
        check(f'unit t{thr}: u50 warnings={w}, log={w}, count=50', a[0] == w and a[1] == w and a[2] == 50, str(a))
        a2 = rd[(f't{thr}', 'u50-second-within-a-minute')]
        check(f'unit t{thr}: second batch warnings={w}, new log lines 0, count=100', a2[0] == w and a2[1] == 0 and a2[2] == 100, str(a2))
        b = rd[(f't{thr}', 'u5')]
        w5 = 1 if 5 > thr else 0
        check(f'unit t{thr}: u5 warnings={w5}, count=5', b[0] == w5 and b[2] == 5, str(b))
        c = rd[(f't{thr}', 'l50-logged')]
        check(f'unit t{thr}: LOGGED 50 no warning, count 50', c[0] == 0 and c[1] == 0 and c[2] == 50, str(c))
    mt = [rd[(f't{t}', 'u50-first')][3] for t in (1, 10, 1000)]
    check('unit: memtable live bytes of the first 50-key batch within 5% across thresholds', min(mt) > 0 and max(mt) <= 1.05 * min(mt), str(mt))
    k = rd[('control', 'u50-size-control')]
    check('unit control: rejected "Batch too large", count 0, memtable 0', 'Batch too large' in k[4] and k[2] == 0 and k[3] == 0, str(k))

# ---- cluster tier
c = d + '/cluster'
if os.path.isdir(c):
    S = open(c + '/summary.txt').read()
    arms = {}
    for a in ('t1', 't10', 't100000', 't10r', 'ctl'):
        ad = f'{c}/{a}'
        if not os.path.isdir(ad):
            continue
        sm = open(ad + '/summary.txt').read()
        load = json.loads(re.search(r'^load (\{.*\})$', sm, re.M).group(1)) if re.search(r'^load \{', sm, re.M) else None
        probe = json.loads(re.search(r'^probe (\{.*\})$', sm, re.M).group(1))
        sl = open(ad + '/system.log', errors='replace').read().splitlines()
        warn = [l for l in sl if l.startswith('WARN') and 'Unlogged batch covering' in l]
        toolarge = [l for l in sl if l.startswith('ERROR') and 'exceeding specified threshold' in l]
        errs = [l for l in sl if l.startswith('ERROR')]
        heap = [int(l.split(',')[1]) for l in list(open(ad + '/heap.csv'))[1:] if l.strip()]
        ds = [l.strip().split(',') for l in list(open(ad + '/dirsize.csv'))[1:] if l.strip()]
        ts = [l.strip().split(',') for l in list(open(ad + '/tablestats.csv'))[1:] if l.strip()]
        cnt = re.search(r'count\(\*\) (\d+)', sm)
        pf = re.search(r"pre-flush \{'memtable_data_size': (\d+)", sm)
        sp = re.search(r"post-flush \{'memtable_data_size': \d+, 'space_live': (\d+)", sm)
        arms[a] = dict(load=load, probe=probe, warn=len(warn), toolarge=len(toolarge), errs=len(errs), heap_peak=max(heap), data_end=int(ds[-1][1]),
                       data_max=max(int(r[1]) for r in ds), clog_max=max(int(r[2]) for r in ds), memtable_max=max(int(r[1]) for r in ts if r[1] != 'None'),
                       count=int(cnt.group(1)) if cnt else None, pre_memtable=int(pf.group(1)), post_space_live=int(sp.group(1)))
        print(f'ARM {a}: ' + json.dumps({k: v for k, v in arms[a].items() if k not in ('load', 'probe')}) + ' load=' + json.dumps({k: load[k] for k in ('ok', 'failed', 'rows', 'warned')}))
    ROWS = 8 * 250 * 500
    for a in ('t1', 't10', 't100000', 't10r'):
        if a not in arms:
            continue
        x = arms[a]; thr = {'t1': 1, 't10': 10, 't100000': 100000, 't10r': 10}[a]
        check(f'cluster {a}: rows acked {ROWS}, failed 0, count(*) {ROWS}', x['load']['rows'] == ROWS and x['load']['failed'] == 0 and x['count'] == ROWS, f"{x['load']['rows']} {x['count']}")
        if thr < 500:
            check(f'cluster {a}: client warning on all 2000 batches; WARN log lines 1..2 (probe + at most one more)', x['load']['warned'] == 2000 and 1 <= x['warn'] <= 2, f"warned={x['load']['warned']} log={x['warn']}")
        else:
            check(f'cluster {a}: no client warning, no WARN log line', x['load']['warned'] == 0 and x['warn'] == 0, f"warned={x['load']['warned']} log={x['warn']}")
        check(f'cluster {a}: no ERROR log lines', x['errs'] == 0, str(x['errs']))
    if 'ctl' in arms:
        x = arms['ctl']
        check('cluster ctl: all 2000 batches rejected, 0 rows, count 0', x['load']['ok'] == 0 and x['load']['failed'] == 2000 and x['count'] == 0)
        check('cluster ctl: node log has 2001 "exceeding specified threshold" ERROR lines (probe + 2000)', x['toolarge'] == 2001, str(x['toolarge']))
    check('cluster ctl: no data and no memtable (data dir < 1% of t10)', 'ctl' not in arms or arms['ctl']['data_max'] < 0.01 * arms['t10']['data_max'], '')
    base = [arms[a] for a in ('t1', 't10', 't100000', 't10r') if a in arms]
    for key in ('heap_peak', 'data_end', 'memtable_max', 'clog_max', 'pre_memtable', 'post_space_live'):
        v = [b[key] for b in base]
        print(f'RATIO {key}: {v} max/min {max(v) / min(v):.3f}')
print('SELFCHECK', 'ALL OK' if ok_all else 'SOME BAD')
