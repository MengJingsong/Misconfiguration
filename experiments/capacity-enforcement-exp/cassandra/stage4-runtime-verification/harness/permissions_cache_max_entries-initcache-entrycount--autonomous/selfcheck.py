#!/usr/bin/env python3
"""Self-check (results section 5): re-reads the raw files with its own parsing, independent of collect-probe.py,
unit-analyze.py and cluster-analyze.py. usage: selfcheck.py <run-dir>   (e.g. /mydata/jingsong-cass-s4/o03/run1)"""
import glob, os, re, sys
R = sys.argv[1]
print('== unit tier (raw: TEST-*.log, junit XML)')
txt = ''
for p in sorted(glob.glob(os.path.join(R, 'unit', 'TEST-*.log*'))):
    # own reassembly: concatenate every [main] message fragment, then search the joined text
    for l in open(p, errors='replace'):
        m = re.match(r'^\S+\s+\[main\] \S+ (.*)$', l.rstrip('\n'))
        txt += m.group(1) if m else '\n'
recs = re.findall(r'PROBE max=(\d+) n=(\d+) estimatedSize=(\d+) asMap=(\d+) loads=(\d+) reloads100=(\d+) heapDeltaMB=(-?[\d.]+)', txt)
for r in recs:
    M, n, size, am, loads, rl, mb = int(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[4]), int(r[5]), float(r[6])
    print(f"unit M={M}: size={size} (min(M,N)={min(M, n)}, equal={size == min(M, n)}) asMap={am} loads={loads} reloads100={rl} "
          f"heapMB={mb} perEntryKB={(mb * 1048576 / size / 1024) if size else 0:.2f}")
print('unit M=-1:', re.findall(r'PROBE max=-1 -> ([^\n]*?IllegalArgumentException[^\n]*?negative)', txt)[:1])
print('unit shrink:', re.findall(r'PROBE shrink 10000->100 before=(\d+) after=(\d+)', txt))
for x in sorted(glob.glob(os.path.join(R, 'unit', 'TEST-*.xml'))):
    h = open(x).read(); m = re.search(r'tests="(\d+)".*?failures="(\d+)"|failures="(\d+)".*?tests="(\d+)"', h, re.S)
    e = re.search(r'errors="(\d+)"', h); f = re.search(r'failures="(\d+)"', h); t = re.search(r'tests="(\d+)"', h)
    print(f"junit {os.path.basename(x)}: tests={t and t.group(1)} failures={f and f.group(1)} errors={e and e.group(1)}")
print('== cluster tier (raw: session.txt, *.hist, system.log, driver.txt)')
C = os.path.join(R, 'cluster')
def hist(p):
    rr = B = tot = None
    for l in open(p):
        w = l.split()
        if len(w) >= 4 and w[0].endswith(':'):
            if w[3] == 'org.apache.cassandra.auth.RoleResource': rr = int(w[1])
            if w[3] == '[B': B = int(w[2])
        if w and w[0] == 'Total': tot = int(w[2])
    return (rr or 0), B, tot
sess = open(os.path.join(C, 'session.txt')).read()
for arm in ('M1000', 'M5000', 'M100000', 'off'):
    A = os.path.join(C, arm)
    blk = sess.split(f'=== arm {arm} ')[1].split('=== arm ')[0]
    esv = dict(re.findall(r'\] (base|after|shrink) EstimatedSize=(\d+)', blk))
    out = {p: hist(os.path.join(A, p + '.hist')) for p in ('base', 'after', 'shrink') if os.path.exists(os.path.join(A, p + '.hist'))}
    b = out['base']
    line = f"{arm}: ES={esv} "
    for p, v in out.items():
        line += f"| {p}: RR={v[0]} dRR={v[0] - b[0]} d[B={(v[1] - b[1]) / 1048576:.2f}MB dTotal={(v[2] - b[2]) / 1048576:.2f}MB "
    print(line)
    sl = open(os.path.join(A, 'system.log'), errors='replace').read()
    inits = re.findall(r'\(Re\)initializing PermissionsCache \(validity period/update interval/max entries/active update\) \(([^)]*)\)', sl)
    print(f"   system.log: PermissionsCache init lines {inits}; '^ERROR' lines {len(re.findall(r'(?m)^ERROR', sl))}; "
          f"OutOfMemoryError {sl.count('java.lang.OutOfMemoryError')}; 'Changed'/setMaximum n/a")
    print(f"   driver: {open(os.path.join(A, 'driver.txt')).read().strip().splitlines()[-1]}; driver Traceback: {'Traceback' in open(os.path.join(A, 'driver.txt')).read()}")
    print(f"   heap_info after: {[l.strip() for l in open(os.path.join(A, 'after.heap')) if 'garbage-first heap' in l]}")
print('daemons left in session:', re.findall(r'our daemons left: (\d+)', sess), 'drop_roles left:', re.findall(r'drop_roles left: (\d+)', sess))
