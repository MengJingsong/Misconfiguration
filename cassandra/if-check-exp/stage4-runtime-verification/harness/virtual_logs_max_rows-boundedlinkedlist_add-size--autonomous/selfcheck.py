#!/usr/bin/env python3
"""Independent re-parse of the committed excerpts of run1 (results/<stem>/run1) against the conclusion's statements (results section 5).
usage: selfcheck.py <run1 folder>.  Prints PASS/FAIL lines; does not use analyze.py."""
import os, re, sys
R = sys.argv[1]
ok = True
def chk(name, cond, detail=''):
    global ok
    ok &= bool(cond)
    print(('PASS ' if cond else 'FAIL ') + name + (' | ' + detail if detail else ''))

# ---- unit tier
def kv(line):
    return dict(re.findall(r'(\S+?)=(\S+)', line))
for f in ['cap-len200', 'cap-len2000', 'cap-adds-lt-size', 'cap-50x']:
    for l in open(f'{R}/unit/{f}.out'):
        d = kv(l)
        if l.startswith('RESULT'):
            size, adds = int(d['size']), int(d['adds'])
            want = min(size, adds)
            chk(f'unit {f} size={size} adds={adds}: dataRows==bufferSize==instances==min(adds,size)',
                int(d['dataRows']) == int(d['bufferSize']) == int(d['logMessageInstances']) == want, f"{d['dataRows']}/{d['bufferSize']}/{d['logMessageInstances']} want {want}")
            if int(d['dataRows']) >= 50000:
                L = int(d['len']); bpr = int(d['bytesPerRow'])
                chk(f'unit {f} size={size} L={L}: bytes per row in [L+80, L+112]', L + 80 <= bpr <= L + 112, f'{bpr}')
        elif l.startswith('size=') and 'newestId' in l:
            size, adds = int(d['size']), int(d['adds']); buf, new, old = int(d['bufferSize']), int(d['newestId']), int(d['oldestId'])
            chk(f'unit {f} checkpoint adds={adds}: buffer={min(size, adds)}, newest={adds}, oldest={max(1, adds - size + 1)}', buf == min(size, adds) and new == adds and old == max(1, adds - size + 1))
for l in open(f'{R}/unit/mt8.out'):
    if l.startswith('RESULT'):
        d = kv(l); chk('unit mt8: final == sampled max == dataRows == 1000', int(d['finalBufferSize']) == int(d['maxSampledBufferSize']) == int(d['dataRows']) == 1000)
want = {'unset': 50000, '999': 50000, '1000': 1000, '1001': 1001, '50000': 50000, '50001': 50001, '100000': 100000, '100001': 50000, '0': 50000, '-1': 50000}
for l in open(f'{R}/unit/resolve-inproc.out'):
    d = kv(l); chk(f"unit resolve in-process {d['value']} -> {want[d['value']]}", int(d['resolved']) == want[d['value']])
for v in ['unset', '999', '1000', '100000', '100001']:
    l = open(f'{R}/unit/resolve-D-{v}.out').read(); d = kv(l)
    chk(f'unit resolve -D {v} -> {want[v]}', int(d['resolved']) == want[v])

# ---- cluster tier
def hist_inst(path):
    for l in open(path):
        if 'LogMessagesTable$LogMessage' in l: return int(l.split()[1])
    return 0
def events(path):
    return int(open(path).read().split('\n')[0].split('=')[1])
NEFF = {'n1000': 1000, 'n20000': 20000, 'n100000': 100000, 'n200000': 50000, 'nunset': 50000, 'off': 0, 'w1000': None}
for arm, neff in NEFF.items():
    D = f'{R}/cluster/{arm}'
    cap = open(f'{D}/capacity-line.txt').read()
    if neff is None: neff = 1000
    chk(f'cluster {arm}: capacity line says {neff if arm != "off" else 50000}', re.search(r'at most (\d+) rows', cap).group(1) == str(neff if arm != 'off' else 50000))
    base_e, base_i = events(f'{D}/base.events'), hist_inst(f'{D}/hist-base.4classes.txt')
    for tag in sorted([f[:-7] for f in os.listdir(D) if f.endswith('.events') and f != 'base.events'], key=lambda x: int(x[1:])):
        e, i = events(f'{D}/{tag}.events'), hist_inst(f'{D}/hist-{tag}.4classes.txt'); rows = int(open(f'{D}/cqlrows-{tag}.txt').read())
        if arm == 'off':
            chk(f'cluster off {tag}: instances 0, rows 0', i == 0 and rows == 0)
        elif arm == 'w1000':
            chk(f'cluster w1000 {tag}: instances == 6 (= WARN/ERROR events of the run) < 1000, events {e}', i == 6 and rows <= i)
        else:
            exp = min(neff, base_i + e - base_e)
            tol = 0.01 * exp if e - base_e + base_i < neff else 5
            chk(f'cluster {arm} {tag}: instances {i} == min(N_eff {neff}, b0+E-e0 = {base_i + e - base_e})', abs(i - exp) <= tol and rows <= i, f'cql rows {rows}')
# eviction evidence: debug.log events at/after the oldest listed timestamp (analysis.txt, column since_old) <= 2N+1000 for the arms that hit the cap
cur = None
for l in open(f'{R}/cluster/analysis.txt'):
    m = re.match(r'=+ (\S+)', l)
    if m: cur = m.group(1); continue
    p = l.split()
    if cur in ('n1000', 'n20000', 'n100000', 'n200000', 'nunset') and len(p) == 8 and p[0].startswith('s') and p[0] != 'base' and p[6].isdigit():
        neff = NEFF[cur]
        if int(p[2]) == neff:
            chk(f'cluster {cur} {p[0]}: events since the oldest listed row {p[6]} <= 2N+1000 (events in the run {p[1]}; ' + ('discriminating' if int(p[1]) > 2 * neff + 1000 else 'not discriminating, events <= 2N+1000') + ')', int(p[6]) <= 2 * neff + 1000)
print('ALL PASS' if ok else 'SOME FAIL')
sys.exit(0 if ok else 1)
