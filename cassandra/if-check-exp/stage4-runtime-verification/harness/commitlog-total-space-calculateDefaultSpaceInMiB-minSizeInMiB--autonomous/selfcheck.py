#!/usr/bin/env python3
"""Independent self-check: re-parses the raw per-arm files (not analyze.py's output) and recomputes the facts the
conclusion rests on. Usage: selfcheck.py <clusterdir> <unitdir>. Exits 1 if any check fails. Prints one line per check.
Cluster facts per arm: effective limit (WARN line / config line), stress rows and errors, peak commit-log bytes from
du.csv (re-parsed), first sample above the limit, flush reasons from system.log, segment deletions from debug.log.gz,
MEMTABLE_LIMIT count, the 90 % volume bound, and that nothing was left running (session.log). Unit facts: PASS/FAIL counts
from cltest.out and the JUnit XMLs."""
import sys, os, re, glob, gzip

root, unit = sys.argv[1], sys.argv[2]
bad = 0
MIB = 1048576


def chk(name, ok, detail=''):
    global bad
    print(('OK   ' if ok else 'FAIL ') + name + ('  ' + detail if detail else ''))
    if not ok:
        bad += 1


# ---------------- unit
lines = open(os.path.join(unit, 'cltest.out')).read().splitlines()
npass = sum(1 for l in lines if l.startswith('RESULT PASS'))
nfail = sum(1 for l in lines if l.startswith('RESULT FAIL'))
done = [l for l in lines if l.startswith('RESULT DONE')]
chk('unit: no FAIL lines, 5 DONE failures=0', nfail == 0 and len(done) == 5 and all('failures=0' in l for l in done), 'pass=%d fail=%d done=%d' % (npass, nfail, len(done)))
for arm in 'HEVCD':
    x = open(os.path.join(unit, 'ant-%s.log' % arm)).read()
    chk('unit: arm %s ant log: Tests run: 1, Failures: 0, Errors: 0, BUILD SUCCESSFUL' % arm, 'Tests run: 1, Failures: 0, Errors: 0' in x and 'BUILD SUCCESSFUL' in x)
init = {}
for l in lines:
    m = re.match(r'RESULT ARM (\w) ', l)
    if m:
        cur = m.group(1)
    m = re.match(r'RESULT INIT commitlog_total_space=(\d+) cdc_total_space=(\d+) warnCommitlog=(\d+) warnCdc=(\d+)', l)
    if m:
        init[cur] = tuple(int(v) for v in m.groups())
chk('unit: H=8192, E=64, V=1024 (+1 WARN), C cdc=512 (+1 WARN), D cdc=4096 (0 WARN)',
    init['H'][0] == 8192 and init['E'][0] == 64 and init['V'][0] == 1024 and init['V'][2] == 1 and init['C'][1] == 512 and init['C'][3] == 1
    and init['D'][1] == 4096 and init['D'][3] == 0 and init['E'][2] == 0, str(init))
# arithmetic: recompute from first principles for the lines the prediction names
want = {'CL 0': 0, 'CL 32767MiB': 8191, 'CL 32768MiB': 8192, 'CL 32769MiB': 8192, 'CL 1TiB': 8192, 'CL 4GiB': 1024,
        'CDC 0': 0, 'CDC 32767MiB': 4095, 'CDC 32768MiB': 4096, 'CDC 1TiB': 4096}
for k, v in want.items():
    n = sum(1 for l in lines if re.match(r'RESULT PASS rep\d %s expected=%d actual=%d$' % (re.escape(k), v, v), l))
    chk('unit: %s -> %d (value on 5 arms x 2 reps)' % (k, v), n == 10 or n == 0 and False, 'n=%d' % n)
# the existing upstream test
ex = open(os.path.join(unit, 'ant-existing.log')).read()
chk('unit: upstream testCalculateDefaultSpaceInMiB passed', 'Tests run: 1, Failures: 0, Errors: 0' in ex)

# ---------------- cluster
peaks = {}
for d in sorted(glob.glob(os.path.join(root, '*-r[0-9]'))):
    arm = os.path.basename(d)
    a, rep = arm.rsplit('-r', 1)
    limit = 1024 if a == 'unset' else int(a)
    chk('%s: DONE and no FAILED/ABORT' % arm, os.path.exists(d + '/DONE') and not os.path.exists(d + '/FAILED') and not os.path.exists(d + '/ABORT'))
    sess = open(d + '/session.log').read()
    chk('%s: no daemon left' % arm, sess.count('daemons left: []') >= 1 and 'WARNING daemon still present' not in sess)
    # effective limit
    if a == 'unset':
        w = open(d + '/system.log').read()
        m = re.search(r"Small commitlog volume detected at '[^']*'; setting commitlog_total_space to (\d+)\.", w)
        chk('%s: WARN sets 1024' % arm, bool(m) and int(m.group(1)) == 1024)
    else:
        w = open(d + '/system.log').read()
        chk('%s: no Small-volume WARN, yaml has the explicit value' % arm, 'Small commitlog volume' not in w and ('commitlog_total_space: %sMiB' % a) in open(d + '/yaml.diff').read())
    so = open(d + '/stress.out').read()
    m1 = re.search(r'Total partitions\s*:\s*([\d,]+)', so); m2 = re.search(r'Total errors\s*:\s*(\d+)', so)
    chk('%s: stress wrote 2,200,000 rows, 0 errors' % arm, m1 and m1.group(1) == '2,200,000' and m2 and m2.group(1) == '0')
    # du.csv re-parse
    samples = []
    for ln in open(d + '/du.csv'):
        p = ln.strip().split(',')
        if len(p) == 5 and all(x.isdigit() for x in p[:4]):
            samples.append((int(p[0]), int(p[1]), int(p[3])))
    tt = dict(x.split('=') for x in open(d + '/times.txt').read().split())
    T0, T1, TS = int(tt['T0']), int(tt['T1']), int(tt['TS'])
    inside = [s for s in samples if T0 - 1000 <= s[0] <= TS]
    pk = max(s[1] for s in inside) / MIB
    peaks[arm] = pk
    gaps = [b[0] - a_[0] for a_, b in zip(inside, inside[1:])]
    chk('%s: sampler gaps <= 2 s (max %d ms), %d samples' % (arm, max(gaps), len(inside)), max(gaps) <= 2000)
    chk('%s: tmpfs used never above 90 %% (max %.0f MiB)' % (arm, max(s[2] for s in samples) / MIB), max(s[2] for s in samples) < 0.9 * 4096 * MIB)
    first = next((s for s in inside if s[1] / MIB > limit), None)
    chk('%s: limit reached (peak %.0f MiB vs limit %d)' % (arm, pk, limit), first is not None or a == '8192' and pk > 0)
    # flush reasons from the raw log
    reasons = {}
    for l in open(d + '/system.log'):
        m = re.search(r'Enqueuing flush of (\S+), Reason: (\w+)', l)
        if m:
            reasons[m.group(2)] = reasons.get(m.group(2), 0) + 1
    chk('%s: MEMTABLE_LIMIT flushes = %d (must be 0)' % (arm, reasons.get('MEMTABLE_LIMIT', 0)), reasons.get('MEMTABLE_LIMIT', 0) == 0, str(reasons))
    dirty = reasons.get('COMMITLOG_DIRTY', 0)
    dl = 0
    p = d + '/debug.log.gz'
    if os.path.exists(p):
        dl = sum(1 for l in gzip.open(p, 'rt', errors='replace') if 'is no longer active and will be deleted' in l)
    print('INFO %s: peak %.1f MiB, COMMITLOG_DIRTY flushes %d, deletions %d, reasons %s' % (arm, pk, dirty, dl, reasons))
    if a == '8192':
        chk('%s: control has no COMMITLOG_DIRTY flush (uncapped)' % arm, dirty == 0)
    else:
        chk('%s: capped arm has COMMITLOG_DIRTY flushes (direct reclaim evidence)' % arm, dirty > 0)
for rep in (1, 2):
    k = lambda a: peaks.get('%s-r%d' % (a, rep))
    if all(k(a) for a in ('unset', '256', '128', '8192')):
        print('INFO rep %d: peaks 128=%.0f 256=%.0f unset(1024)=%.0f control8192=%.0f; ordered=%s' % (rep, k('128'), k('256'), k('unset'), k('8192'), k('128') < k('256') < k('unset') < k('8192')))
print('selfcheck: %d failed' % bad)
sys.exit(1 if bad else 0)
