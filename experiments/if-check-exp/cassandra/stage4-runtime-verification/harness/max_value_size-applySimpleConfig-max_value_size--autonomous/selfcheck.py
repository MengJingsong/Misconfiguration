#!/usr/bin/env python3
"""Independent self-check of run 1 of max_value_size-applySimpleConfig-max_value_size--autonomous (results §5).
Re-reads the raw files only (never summary.txt): unit  p1-<v>.out, p2-<v>.out;  cluster  req.txt, written.json and per start
system.log, node.out, alloc.trace. Re-derives every B2f / B3f prediction (as amended 2026-10-25) and prints one line per check:
  CHECK <ok|FAIL> <name> :: <detail>
usage: selfcheck.py <unit log dir> <cluster log dir>"""
import json, os, re, sys

U, K = sys.argv[1], sys.argv[2]
n_ok = n_fail = 0


def check(name, cond, detail=''):
    global n_ok, n_fail
    if cond:
        n_ok += 1
    else:
        n_fail += 1
    print('CHECK %s %s :: %s' % ('ok' if cond else 'FAIL', name, detail))


def read(p):
    try:
        return open(p, errors='replace').read()
    except FileNotFoundError:
        return ''


# ---------------- unit: ConfigProbe ----------------
P1 = {'0MiB': 'REJECT ConfigurationException: max_value_size must be positive',
      '2048MiB': 'REJECT ConfigurationException: max_value_size must be smaller than 2048, but was 2048MiB',
      '1MiB': 'OK getMaxValueSize=1048576', '2047MiB': 'OK getMaxValueSize=2146435072', 'unset': 'OK getMaxValueSize=268435456'}
for v, exp in P1.items():
    lines = [l for l in read(os.path.join(U, 'p1-%s.out' % v)).splitlines() if l.startswith(('OK ', 'REJECT '))]
    got = lines[0] if lines else '(none)'
    check('unit.p1.%s' % v, got.startswith(exp), got[:200])

# ---------------- unit: ValueReadProbe ----------------
VB = {'1MiB': 1048576, '4MiB': 4194304, 'unset': 268435456}
SLACK = 65536
MSG = 'Corrupt value length %d encountered, as it exceeds the maximum of %d, which is set via max_value_size in cassandra.yaml'
for v, V in VB.items():
    txt = read(os.path.join(U, 'p2-%s.out' % v))
    rb = re.search(r'STAGE4 readback label=\S+ getMaxValueSize=(\d+) allocSupported=(\w+) allocEnabled=(\w+)', txt)
    check('unit.p2.%s.readback' % v, rb is not None and int(rb.group(1)) == V and rb.group(2) == 'true' and rb.group(3) == 'true',
          rb.group(0) if rb else 'no readback line')
    calls = {}
    for m in re.finditer(r'STAGE4 call phase=(\w+) len=(\d+) limit=(\d+) outcome=(\w+) (.*)', txt):
        calls[(m.group(1), int(m.group(2)))] = (int(m.group(3)), m.group(4), m.group(5))
    maxdelta = 0
    for ln in (V - 1, V, V + 1, 64 << 20):
        c = calls.get(('cap', ln))
        if c is None:
            check('unit.p2.%s.cap.%d' % (v, ln), False, 'missing'); continue
        limit, outcome, rest = c
        d = int(re.search(r'delta=(\d+)', rest).group(1))
        maxdelta = max(maxdelta, d)
        if ln <= V:
            r = re.search(r'remaining=(\d+)', rest)
            check('unit.p2.%s.cap.%d' % (v, ln), limit == V and outcome == 'RETURNED' and r and int(r.group(1)) == ln and ln <= d < ln + SLACK,
                  'limit=%d %s remaining=%s delta=%d' % (limit, outcome, r.group(1) if r else None, d))
        else:
            e = re.search(r'exc=(\S+) msg=(.*?) info_runtime', rest)
            check('unit.p2.%s.cap.%d' % (v, ln), limit == V and outcome == 'THREW' and e and e.group(1) == 'java.io.IOException'
                  and e.group(2) == MSG % (ln, V) and d < SLACK,
                  'limit=%d %s exc=%s delta=%d msg_exact=%s' % (limit, outcome, e.group(1) if e else None, d, bool(e and e.group(2) == MSG % (ln, V))))
    check('unit.p2.%s.max_delta_below_V+64KiB' % v, maxdelta < V + SLACK, 'max delta %d, V %d' % (maxdelta, V))
    for ln in (V + 1, 64 << 20):
        c = calls.get(('control', ln))
        ok = c is not None and c[0] == 2147483647 and c[1] == 'RETURNED' and int(re.search(r'remaining=(\d+)', c[2]).group(1)) == ln \
            and int(re.search(r'delta=(\d+)', c[2]).group(1)) >= ln
        check('unit.p2.%s.control.%d' % (v, ln), ok, str(c)[:160])
    check('unit.p2.%s.done' % v, 'STAGE4 done' in txt)

# ---------------- cluster ----------------
reqs = []
for l in read(os.path.join(K, 'req.txt')).splitlines():
    d = dict(re.findall(r'(\w+)=(\S+)', l.split(' msg=')[0]))
    d['msg'] = l.split(' msg=', 1)[1] if ' msg=' in l else ''
    reqs.append(d)
written = {int(k): v for k, v in json.load(open(os.path.join(K, 'written.json'))).items()}
SIZES = {1: 524288, 2: 4194304, 3: 12582912, 4: 1048576, 5: 1048577, 6: 8388608, 7: 8388609, 8: 2097152}
check('cluster.written.sizes', all(written.get(k, [None])[0] == n for k, n in SIZES.items()), str({k: v[0] for k, v in written.items()}))

# (i) refusals
for lab, msg in (('z0', 'max_value_size must be positive'), ('z2048', 'max_value_size must be smaller than 2048, but was 2048MiB')):
    out = read(os.path.join(K, lab, 'node.out')) + read(os.path.join(K, lab, 'system.log'))
    check('cluster.%s.refused' % lab, msg in out and 'Startup complete' not in out, 'message present=%s startup_complete=%s' % (msg in out, 'Startup complete' in out))
cl = read(os.path.join(K, 'commands.log'))
for lab in ('z0', 'z2048'):
    m = re.search(r'REFUSAL %s rc=(\d+) secs=(\d+)' % lab, cl)
    check('cluster.%s.rc3' % lab, m is not None and m.group(1) == '3' and int(m.group(2)) <= 120, m.group(0) if m else 'no REFUSAL line in commands.log')


def R(start, op, k=None):
    return [r for r in reqs if r.get('start') == start and r.get('op') == op and (k is None or r.get('k') == str(k))]


def trace(start):
    out = []
    for l in read(os.path.join(K, start, 'alloc.trace')).splitlines():
        m = re.search(r'length=(\d+) thread=(.*) ms=(\d+)$', l)
        if m:
            out.append((int(m.group(1)), int(m.group(3)), m.group(2)))
    return out


# (ii) settings
for lab, val in (('p1', '256MiB'), ('r1', '1MiB'), ('r8', '8MiB'), ('r256', '256MiB')):
    s = R(lab, 'settings')
    check('cluster.%s.settings' % lab, len(s) == 1 and s[0].get('value') == val, str(s[0].get('value') if s else None))
# (iii) p1 inserts
for k in range(1, 8):
    r = R('p1', 'insert', k)
    check('cluster.p1.insert.%d' % k, len(r) == 1 and r[0]['outcome'] == 'OK' and int(r[0]['len']) == SIZES[k], str(r[0] if r else None)[:120])
# (iv) start-up of phase-2 starts
for lab in ('r1', 'r8', 'r256'):
    log = read(os.path.join(K, lab, 'system.log'))
    pre = log.split('Startup complete')[0] if 'Startup complete' in log else log
    check('cluster.%s.startup' % lab, 'Startup complete' in log and 'Corrupt value length' not in pre,
          'startup_complete=%s corrupt_before=%d replay=%s' % ('Startup complete' in log, pre.count('Corrupt value length'),
                                                              (re.findall(r'Log replay complete[^\n]*|No commitlog files found[^\n]*', log) or ['?'])[0]))

GUARD = re.compile(r'Corrupt value length (\d+) encountered, as it exceeds the maximum of (\d+)')


def phase2(lab, V, keys):
    log = read(os.path.join(K, lab, 'system.log'))
    guards = {(int(a), int(b)) for a, b in GUARD.findall(log)}
    tr = trace(lab)
    refused = []
    for k in keys:
        r = R(lab, 'read', k)
        if len(r) != 1:
            check('cluster.%s.read.%d' % (lab, k), False, 'found %d requests' % len(r)); continue
        r = r[0]; n = SIZES[k]
        t0, t1 = int(r['t0']), int(r['t1'])
        inwin = [t for t in tr if t[0] == n and t0 - 50 <= t[1] <= t1 + 50]
        if n <= V:
            check('cluster.%s.read.%d.accepted' % (lab, k), r['outcome'] == 'OK' and r.get('len') == str(n) and r.get('match') == 'yes' and len(inwin) >= 1,
                  'outcome=%s len=%s match=%s alloc_in_window=%d' % (r['outcome'], r.get('len'), r.get('match'), len(inwin)))
        else:
            refused.append(n)
            if k == 8 and lab == 'r1':
                ok = r['outcome'] == 'ERR' and ((n, V) in guards or ('Corrupt value length %d' % n) in r['msg']) and not inwin
                check('cluster.r1.read.8.refused_memtable', ok, 'class=%s guard_in_log=%s guard_in_msg=%s alloc_in_window=%d' %
                      (r.get('class'), (n, V) in guards, ('Corrupt value length %d' % n) in r['msg'], len(inwin)))
            else:
                anytime = [t for t in tr if t[0] == n]
                ok = r['outcome'] == 'ERR' and r.get('class') == 'ReadFailure' and (n, V) in guards and not anytime
                check('cluster.%s.read.%d.refused' % (lab, k), ok, 'class=%s guard(%d,%d)_in_log=%s alloc_of_len_anytime=%d' %
                      (r.get('class'), n, V, (n, V) in guards, len(anytime)))
    return log, guards, refused


log1, g1, ref1 = phase2('r1', 1048576, [1, 2, 3, 4, 5, 6, 7, 8])
ins8 = R('r1', 'insert', 8)
check('cluster.r1.insert.8.acknowledged', len(ins8) == 1 and ins8[0]['outcome'] == 'OK', str(ins8[0] if ins8 else None)[:120])
check('cluster.r1.corruptsstable_present', 'CorruptSSTableException' in log1, '')
ra = R('r1', 'readall')
check('cluster.r1.readall.fails', len(ra) == 1 and ra[0]['outcome'] == 'ERR', str(ra[0].get('class') if ra else None))
log8, g8, ref8 = phase2('r8', 8388608, [1, 2, 3, 4, 5, 6, 7, 8])
ra = R('r8', 'readall')
check('cluster.r8.readall.fails', len(ra) == 1 and ra[0]['outcome'] == 'ERR', str(ra[0].get('class') if ra else None))
log256, g256, ref256 = phase2('r256', 268435456, [1, 2, 3, 4, 5, 6, 7, 8])
check('cluster.r256.no_guard_line', 'Corrupt value length' not in log256, '')
ra = R('r256', 'readall')
exp_rows = ','.join('%d:%d:yes' % (k, SIZES[k]) for k in sorted(SIZES))
check('cluster.r256.readall.8rows', len(ra) == 1 and ra[0]['outcome'] == 'OK' and ra[0].get('nrows') == '8' and ra[0].get('rows') == exp_rows,
      str(ra[0].get('rows') if ra else None))
# ceiling follows the knob
for lab, exp in (('r1', 1048576), ('r8', 8388608), ('r256', 12582912)):
    got = max([int(r['len']) for r in R(lab, 'read') if r['outcome'] == 'OK' and r.get('len', 'none') != 'none'] or [0])
    check('cluster.%s.ceiling' % lab, got == exp, 'largest value read back %d (expected %d)' % (got, exp))
# INFO: trace counts per accepted read (source: 2)
for lab in ('r1', 'r8', 'r256'):
    tr = trace(lab); cnt = []
    for r in R(lab, 'read'):
        if r['outcome'] == 'OK':
            n = int(r['len']); t0, t1 = int(r['t0']), int(r['t1'])
            cnt.append('%s:%d' % (r['k'], len([t for t in tr if t[0] == n and t0 - 50 <= t[1] <= t1 + 50])))
    print('INFO %s alloc lines per accepted read (k:count): %s' % (lab, ' '.join(cnt)))
print('INFO r1 read 8 class: %s' % (R('r1', 'read', 8)[0].get('class') if R('r1', 'read', 8) else None))
print('SELFCHECK %d ok, %d FAIL' % (n_ok, n_fail))
