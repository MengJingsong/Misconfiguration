#!/usr/bin/env python3
"""Self-check (results section 5) for MAX_KEY_SIZE-write-limit-2--autonomous.
Re-parses the raw surefire -output.txt (unit) and the cluster-run.log IFCHK lines (cluster), not the run scripts'
summaries, and prints PASS/FAIL against the frozen B2f/B2g (A3, A4) and B3f/B3g (A8).
Usage: python3 -I selfcheck.py <logs-dir>   (<logs-dir> holds unit/ and cluster/)"""
import glob
import os
import re
import sys

d = sys.argv[1]
fails = 0
passes = 0


def chk(name, ok, val):
    global fails, passes
    if ok:
        passes += 1
    else:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + ": " + str(val))


def kv(line):
    out = {}
    for part in line.strip().split(',')[2:]:
        if '=' in part:
            k, v = part.split('=', 1)
            out[k] = v
    return out


uf = glob.glob(os.path.join(d, 'unit', '*TestBoundedLimitMemory-output.txt'))
lines = open(uf[0], errors='replace').read().splitlines() if uf else []
lines = [l for l in lines if l.startswith('IFCHK,')]
print("unit source:", uf[0] if uf else None, len(lines), "IFCHK lines")
rep = glob.glob(os.path.join(d, 'unit', 'org.apache.hadoop.io.TestBoundedLimitMemory.txt'))
if rep:
    t = open(rep[0]).read()
    chk('surefire TestBoundedLimitMemory 6/0/0', 'Tests run: 6, Failures: 0, Errors: 0, Skipped: 0' in t,
        re.findall(r'Tests run:.*', t)[:1])
for name in ['org.apache.hadoop.io.TestBoundedByteArrayOutputStream.txt',
             'org.apache.hadoop.io.file.tfile.TestTFileStreams.txt']:
    f = os.path.join(d, 'unit', name)
    t = open(f).read() if os.path.exists(f) else ''
    m = re.search(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+)', t)
    chk('existing ' + name, bool(m) and m.group(2) == '0' and m.group(3) == '0' and int(m.group(1)) > 0,
        m.group(0) if m else 'missing')

by = {}
for l in lines:
    by.setdefault(l.split(',')[1], []).append(kv(l))
ins = by.get('instr', [{}])[0]
chk('instrument supported/enabled', ins.get('supported') == 'true' and ins.get('enabled') == 'true', ins)
chk('instrument known answer 1 MiB in [1048576, 1048576+64]',
    1048576 <= int(ins.get('knownAnswer1MiB', -1)) <= 1048640, ins.get('knownAnswer1MiB'))

exp1 = {1024: (1, 1000), 32768: (32, 32000), 65536: (65, 65000)}
for r in by.get('U1', []):
    lim = int(r['lim'])
    w, sz = exp1[lim]
    chk('U1 lim=%d writes=%d size=%d msg frame' % (lim, w, sz),
        int(r['writes']) == w and int(r['size']) == sz and r['msg'] == 'Reach the limit of the buffer'
        and r['frame'] == 'BoundedByteArrayOutputStream.write:92', r)
chk('U1 rows = 3', len(by.get('U1', [])) == 3, len(by.get('U1', [])))

u2 = by.get('U2', [])
chk('U2 rows = 3', len(u2) == 3, len(u2))
if u2:
    cs = [int(r['ctorAllocMedian']) for r in u2]
    ws = [int(r['writeAllocMedian']) for r in u2]
    for r in u2:
        c = int(r['ctorAllocMedian'])
        chk('U2 lim=%s ctorAlloc in [1048576, 1048576+1024]' % r['lim'], 1048576 <= c <= 1048576 + 1024, c)
        chk('U2 lim=%s writeAlloc < 4096' % r['lim'], int(r['writeAllocMedian']) < 4096, r['writeAllocMedian'])
        chk('U2 lim=%s frame write:92' % r['lim'], r['frame'] == 'BoundedByteArrayOutputStream.write:92', r['frame'])
    chk('U2 ctorAlloc spread <= 1024 (flat)', max(cs) - min(cs) <= 1024, max(cs) - min(cs))
    chk('U2 refute test: spread >= 524288 NOT met', max(cs) - min(cs) < 524288 and max(ws) - min(ws) < 524288,
        (max(cs) - min(cs), max(ws) - min(ws)))
    for r in u2:
        chk('U2 lim=%s writeAlloc < size at EOF (no growth with bytes written)' % r['lim'],
            int(r['writeAllocMedian']) < int(r['size']), (r['writeAllocMedian'], r['size']))

for r in by.get('U3', []):
    cap = int(r['cap'])
    c = int(r['ctorAllocMedian'])
    chk('U3 cap=%d ctorAlloc in [cap, cap+1024]' % cap, cap <= c <= cap + 1024, c)
u3 = by.get('U3', [])
if len(u3) == 3:
    chk('U3 follows cap (16Mi/64Ki ratio > 200)', int(u3[2]['ctorAllocMedian']) / int(u3[0]['ctorAllocMedian']) > 200,
        int(u3[2]['ctorAllocMedian']) / int(u3[0]['ctorAllocMedian']))
for r in by.get('U3b', []):
    a = int(r['allocMedian'])
    chk('U3b alloc >= 204800', a >= 204800, a)

u4 = [r for r in by.get('U4', []) if r.get('keyPrepare') == '-1']
u4b = [r for r in by.get('U4', []) if r.get('keyPrepare') == '65537']
if u4:
    r = u4[0]
    chk('U4 64 writes ok, 65th throws at write:92', r['writesOk'] == '64' and r['attempt'] == '65'
        and r['msg'] == 'Reach the limit of the buffer' and r['frame'] == 'BoundedByteArrayOutputStream.write:92', r)
    chk('U4 Writer ctorAlloc >= 131104', int(r['ctorAllocMedian']) >= 131104, r['ctorAllocMedian'])
    chk('U4 writeAlloc < 8192', int(r['writeAllocMedian']) < 8192, r['writeAllocMedian'])
else:
    chk('U4 row present', False, None)
chk('U4 prepareAppendKey(65537) -> IndexOutOfBoundsException',
    bool(u4b) and u4b[0]['exception'] == 'java.lang.IndexOutOfBoundsException', u4b)

u5 = {int(r['N']): int(r['fileLength']) for r in by.get('U5', [])}
if set(u5) == {1, 10, 100}:
    s1 = (u5[10] - u5[1]) / 9.0
    s2 = (u5[100] - u5[10]) / 90.0
    chk('U5 slopes agree within 5%', abs(s1 - s2) / s2 <= 0.05, (u5, round(s1, 1), round(s2, 1)))
    chk('U5 len(100) >= 100 x 65536', u5[100] >= 6553600, u5[100])
    for n, lo, hi in [(1, 190000, 205000), (10, 1340000, 1420000), (100, 13000000, 13400000)]:
        chk('U5 N=%d near amended prediction (2N+1) x 65.5 KB' % n, lo <= u5[n] <= hi, u5[n])
else:
    chk('U5 rows', False, u5)

# ---- cluster ----
cl = os.path.join(d, 'cluster', 'cluster-run.log')
if os.path.exists(cl):
    cls = [l for l in open(cl, errors='replace').read().splitlines() if l.startswith('IFCHK,')]
    rows = {}
    for l in cls:
        k = l.split(',')
        if k[1] == 'cluster':
            rows[k[2]] = kv(l)
        else:
            rows[k[1]] = kv(l)
    MIB = 1048576
    agg = {}
    for lab, n in [('A1M', MIB), ('A16M', 16 * MIB), ('A64M', 64 * MIB)]:
        r = rows.get(lab)
        if not r:
            chk('cluster %s present' % lab, False, None)
            continue
        a = int(r['aggBytes'])
        agg[n] = a
        chk('%s final SUCCEEDED, aggregation SUCCEEDED' % lab, r['final'] == 'SUCCEEDED' and r['aggStatus'] == 'SUCCEEDED',
            (r['final'], r['aggStatus']))
        chk('%s agg >= 2N' % lab, a >= 2 * n, (a, 2 * n))
        chk('%s read-back = N for both workers' % lab, int(r['readBack2']) == n and int(r['readBack3']) == n,
            (r['readBack2'], r['readBack3']))
        chk('%s limit message 0 (NM log, yarn logs)' % lab, r['limitMsgNM'] == '0' and r['limitMsgYarnLogs'] == '0',
            (r['limitMsgNM'], r['limitMsgYarnLogs']))
        chk('%s agg vs local raw logs (agg >= local - 64 KiB)' % lab, a >= int(r['localBytes']) - 65536,
            (a, r['localBytes']))
    if len(agg) == 3:
        s1 = (agg[16 * MIB] - agg[MIB]) / (15.0 * MIB)
        s2 = (agg[64 * MIB] - agg[16 * MIB]) / (48.0 * MIB)
        chk('A slopes in [1.9, 2.1]', 1.9 <= s1 <= 2.1 and 1.9 <= s2 <= 2.1, (round(s1, 4), round(s2, 4)))
    r = rows.get('CTRL64M')
    q = rows.get('ctrlquota')
    if r and q:
        a = int(r['aggBytes'])
        chk('control agg <= 33554432', a <= 33554432, a)
        chk('control aggregation not SUCCEEDED', r['aggStatus'] != 'SUCCEEDED', r['aggStatus'])
        chk('control DSQuotaExceeded in NM log >= 1', int(q['quotaLinesNM']) >= 1, q['quotaLinesNM'])
        chk('control limit message 0', r['limitMsgNM'] == '0', r['limitMsgNM'])
    else:
        chk('control rows present', False, (r, q))
    b = rows.get('clusterB')
    if b:
        print('INFO B (secondary): ', b)
        chk('B job succeeded', b['final'] == 'SUCCEEDED' and b['success'] == 'yes', (b['final'], b['success']))
        chk('B >= 1 Memory-to-Memory merge initiated', int(b['initMerges']) >= 1, b['initMerges'])
        chk('B limit message 0', b['limitMsgSyslog'] == '0' and b['limitMsgNM'] == '0',
            (b['limitMsgSyslog'], b['limitMsgNM']))
    else:
        chk('B row present', False, None)
print('TOTAL PASS %d FAIL %d' % (passes, fails))
