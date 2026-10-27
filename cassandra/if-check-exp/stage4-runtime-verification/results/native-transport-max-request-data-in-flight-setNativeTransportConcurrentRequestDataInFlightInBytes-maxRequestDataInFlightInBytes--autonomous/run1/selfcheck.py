#!/usr/bin/env python3
"""Independent self-check of run 1, cluster tier. Re-parses the RAW files of every arm (base.csv, run.csv, times.txt, client.txt, hold.trace,
limits.txt, logs/system.log, yaml.diff, run.log) without importing reduce.py, recomputes the readings, compares them with the
reduce.py summary.txt of the same arm, checks the run's validity conditions, and evaluates the frozen verdict lines C1-C8 (amended B3g)
from the recomputed numbers.  usage: selfcheck.py LOGDIR [PASS_PREFIX]      LOGDIR = pc12:~/s4-b8-cr-logs/cluster"""
import csv, glob, os, re, statistics, sys
MiB = 1048576
D = sys.argv[1]
LV = {'16MiB': 16 * MiB, '64MiB': 64 * MiB, 'default': 107374182, '1GiB': 1 << 30}
OFFER = {'v4-256k': 1000 * 262144, 'v5-256k': 1000 * 262144, 'v5-100k': 2560 * 100000}
def num(s):
    return int(s)
def read(label):
    d = os.path.join(D, label)
    r = {'label': label}
    t = dict(x.split('=') for x in open(d + '/times.txt').read().split())
    base = list(csv.reader(open(d + '/base.csv')))[1:]
    run = list(csv.reader(open(d + '/run.csv')))[1:]
    base = [[int(c) for c in row] for row in base if len(row) == 6 and row[0].isdigit()]
    run = [[int(c) for c in row] for row in run if len(row) == 6 and row[0].isdigit()]
    p0, c0, c1 = int(t['probe_start_ms']), int(t['client_start_ms']), int(t['client_end_ms'])
    r['times'] = t
    bd = statistics.median(row[3] for row in base)
    r['base_direct'] = bd
    r['base_rs_max'] = max(row[1] for row in base)
    load = [row for row in run if c0 - p0 <= row[0] <= c1 - p0]
    r['load_rows'] = len(load)
    r['peak_rs'] = max(row[1] for row in load)
    r['peak_rs_anywhere'] = max(row[1] for row in run)
    r['max_paused'] = max(row[2] for row in load)
    r['min_paused'] = min(row[2] for row in run)
    r['peak_direct'] = max(row[3] for row in load)
    r['peak_direct_anywhere'] = max(row[3] for row in run)
    r['delta'] = r['peak_direct'] - bd
    r['delta_anywhere'] = r['peak_direct_anywhere'] - bd
    r['rs_series'] = [(row[0], row[1]) for row in run]
    cl = open(d + '/client.txt').read()
    m = re.search(r'^TOTAL sent=(\d+) ok=(\d+) warned=(\d+) ovl_bytes=(\d+) ovl_other=(\d+) err=(\d+) outstanding=(\d+)', cl, re.M)
    r['client'] = dict(zip(('sent', 'ok', 'warned', 'ovl_bytes', 'ovl_other', 'err', 'outstanding'), map(int, m.groups()))) if m else None
    r['hold_lines'] = sum(1 for _ in open(d + '/hold.trace'))
    lim = dict(x.split('=') for x in open(d + '/limits.txt').read().split())
    r['limit_start'] = int(lim['global_limit_start'])
    log = open(d + '/logs/system.log', errors='replace').read()
    r['oom'] = len(re.findall(r'java\.lang\.OutOfMemoryError|Direct buffer memory|Out of memory|OutOfMemoryError:', log, re.I))   # the JVM-arguments line also contains -XX:+HeapDumpOnOutOfMemoryError: not matched
    r['errors'] = len(re.findall(r'^ERROR', log, re.M))
    rl = open(d + '/run.log').read()
    r['jvm'] = {k: (k in rl) for k in ('-Dio.netty.maxDirectMemory=0', '-XX:MaxDirectMemorySize=4g', '-Xmx1G', 'hold-request.btm')}
    r['first_trigger'] = 'first trigger: hold rule fired' in rl
    r['summary'] = dict(l.rstrip().split('=', 1) for l in open(d + '/summary.txt') if '=' in l and not l.startswith('EXPECTED'))
    return r
def lab(label):
    m = re.match(r'(p\d)-(live|16MiB|64MiB|default|1GiB)-(v4-256k|v5-100k|v5-256k)', label)
    return m.groups()
arms = {}
for d in sorted(glob.glob(D + '/p*-*')):
    label = os.path.basename(d)
    if not os.path.exists(d + '/summary.txt'): print('NO SUMMARY', label); continue
    p, L, arm = lab(label)
    arms[label] = (p, L, arm, read(label))
ok_all = True
def chk(name, cond, detail=''):
    global ok_all
    ok_all &= bool(cond)
    print('  %-4s %s %s' % ('OK' if cond else 'FAIL', name, detail))
print('== per-arm recompute vs summary.txt, validity')
for label, (p, L, arm, r) in arms.items():
    s = r['summary']
    print(label)
    chk('peak_requests_size equals reduce.py', int(s['peak_requests_size']) == r['peak_rs'], '%d vs %s' % (r['peak_rs'], s['peak_requests_size']))
    chk('delta equals reduce.py', abs(float(s['delta_direct_MiB']) - r['delta'] / MiB) < 0.01, '%.2f vs %s MiB' % (r['delta'] / MiB, s['delta_direct_MiB']))
    chk('max_paused equals reduce.py', int(s['max_paused']) == r['max_paused'], '%d vs %s' % (r['max_paused'], s['max_paused']))
    chk('limit at start matches the arm', r['limit_start'] == (1 << 30 if L == 'live' else LV[L]), str(r['limit_start']))
    chk('JVM args present (netty direct=0, MaxDirect 4g, Xmx1G, Byteman rule)', all(r['jvm'].values()), str(r['jvm']))
    chk('first trigger passed, hold lines == requests sent', r['first_trigger'] and r['client'] and r['hold_lines'] == r['client']['sent'], '%d hold, %s sent' % (r['hold_lines'], r['client'] and r['client']['sent']))
    chk('client drained, no error', r['client'] and r['client']['outstanding'] == 0 and r['client']['err'] == 0 and r['client']['ovl_other'] == 0, str(r['client']))
    chk('no OOM / ERROR in system.log', r['oom'] == 0 and r['errors'] == 0, 'oom %d error %d' % (r['oom'], r['errors']))
    chk('baseline idle (RequestsSize 0)', r['base_rs_max'] == 0)
    chk('peak outside the load window not larger (RS)', r['peak_rs_anywhere'] == r['peak_rs'], '%d vs %d' % (r['peak_rs_anywhere'], r['peak_rs']))
print('\n== frozen predictions per arm (amended B3f)')
res = {}
for label, (p, L, arm, r) in arms.items():
    if L in ('live',): continue
    lim = LV[L]; off = OFFER[arm]
    res[label] = dict(p=p, L=L, arm=arm, rs=r['peak_rs'], d=r['delta'], paused=r['max_paused'], warned=r['client']['warned'], limit=lim,
                      P0=r['peak_rs'] >= 0.9 * lim, P1=r['peak_rs'] <= lim + 4 * MiB, P2=r['delta'] <= 1.5 * lim + 6 * MiB, P3=r['max_paused'] >= 1,
                      ctl_reach=r['peak_rs'] >= 0.8 * off, ctl_nopause=r['max_paused'] == 0)
    x = res[label]
    print('%-26s RS %7.2f MiB (%.3f L)  delta %8.2f MiB (bound %.1f)  paused %d  warned %d  P0 %s P1 %s P2 %s P3 %s' % (
        label, x['rs'] / MiB, x['rs'] / x['limit'], x['d'] / MiB, (1.5 * lim + 6 * MiB) / MiB, x['paused'], x['warned'], x['P0'], x['P1'], x['P2'], x['P3']))
print('\n== ordering and control, per arm type and pass')
for p in sorted({v['p'] for v in res.values()}):
    for arm in ('v4-256k', 'v5-100k', 'v5-256k'):
        ds = {v['L']: v['d'] for v in res.values() if v['p'] == p and v['arm'] == arm}
        if len(ds) < 2: continue
        seq = [ds[k] / MiB for k in ('16MiB', '64MiB', 'default', '1GiB') if k in ds]
        print(p, arm, 'delta MiB by L (16, 64, default, 1GiB):', ['%.1f' % v for v in seq],
              'strictly increasing' if all(a < b for a, b in zip(seq, seq[1:])) else 'NOT strictly increasing',
              '| control >= 2 x 16MiB:' , (ds.get('1GiB', 0) >= 2 * ds['16MiB']) if '1GiB' in ds and '16MiB' in ds else 'n/a')
print('\n== live arm')
for label, (p, L, arm, r) in arms.items():
    if L != 'live': continue
    t = r['times']; p0 = int(t['probe_start_ms']); set_ms = int(t['live_set_ms']) - p0; done_ms = int(t['live_set_done_ms']) - p0; c1 = int(t['client_end_ms']) - p0
    pre = [rs for ts, rs in r['rs_series'] if ts < set_ms and ts >= int(t['client_start_ms']) - p0]
    post = [(ts, rs) for ts, rs in r['rs_series'] if done_ms <= ts <= c1]
    first = next((ts for ts, rs in post if rs <= 20 * MiB), None)
    after = [rs for ts, rs in post if first is not None and ts >= first]
    chk('before the set peak >= 0.8 offered', max(pre) >= 0.8 * OFFER[arm], '%.1f MiB' % (max(pre) / MiB))
    chk('set read back 16777216', '16777216' in open(os.path.join(D, label, 'live-set.txt')).read())
    chk('reaches <= 20 MiB within 90 s of the set', first is not None and first - done_ms <= 90000, 'at +%s s' % (None if first is None else (first - done_ms) / 1000))
    chk('stays <= 20 MiB afterwards (load still running)', after and max(after) <= 20 * MiB, 'max %.2f MiB over %d samples' % (max(after) / MiB if after else -1, len(after)))
    seg = [(ts, rs) for ts, rs in post if first is None or ts <= first]
    chk('no new admission while above the new limit: RS non-increasing from the set until it first reaches <= 20 MiB',
        len(seg) > 10 and all(b <= a for (_, a), (_, b) in zip(seg, seg[1:])), 'up-steps: %d over %d samples' % (sum(1 for (_, a), (_, b) in zip(seg, seg[1:]) if b > a), len(seg)))
print('\nALL-CHECKS-OK' if ok_all else '\nSOME-CHECK-FAILED')
