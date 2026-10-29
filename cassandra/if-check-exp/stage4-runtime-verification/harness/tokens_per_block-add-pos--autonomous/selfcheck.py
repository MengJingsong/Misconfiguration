#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files of tokens_per_block-add-pos--autonomous (regexes on the raw text).  usage: selfcheck.py <unit-dir> [<cluster-root>]"""
import glob, math, os, re, sys

bad = 0


def chk(name, ok, detail=''):
    global bad
    print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + detail if detail else ''))
    bad += (not ok)


ud = sys.argv[1]
txt = {os.path.basename(f)[:-4]: open(f).read() for f in glob.glob(ud + '/*.out')}
chk('unit: 48 outputs (2 arms x 3 reps x (5 tree + 3 ctl))', len(txt) == 48, str(len(txt)))
s = open(ud + '/summary.txt').read()
chk('unit: all 48 cells and the upstream run exit 0; upstream TokenTreeTest 14 pass (the daemon check at the end of the unit run overlapped the node of the cluster-engine instrument check, started 18:07, so its line is absent)', s.count('exit=0') >= 49 and 'Tests run: 14, Failures: 0, Errors: 0' in s)
g = lambda t, k: int(re.search(k + r'=(-?\d+)', t).group(1))
for arm, c in (('stock', 248), ('v124', 124)):
    for rep in (1, 2, 3):
        for n in (248, 249, 2480, 61504, 246016):
            t = txt[f'{arm}-tree-{n}-r{rep}']
            ok = g(t, 'TOKENS_PER_BLOCK') == c and g(t, 'tokenCount') == n and g(t, 'maxInteriorTokens') <= c and g(t, 'maxLeafTokens') <= c and g(t, 'serializedSize') == g(t, 'writtenBytes')
            chk(f'{arm} r{rep} N={n}: constant {c}, no token dropped, nodes <= constant, serialized == written', ok)
            nb = g(t, 'numBlocks')
            chk(f'{arm} r{rep} N={n}: blocks {nb} {"== 1" if n <= c else "in [ceil(N/c), 1.1 ceil(N/c)+3]"}', nb == 1 if n <= c else math.ceil(n / c) <= nb <= 1.1 * math.ceil(n / c) + 3)
for rep in (1, 2, 3):
    a, b = g(txt[f'stock-tree-246016-r{rep}'], 'retainedHeap'), g(txt[f'v124-tree-246016-r{rep}'], 'retainedHeap')
    chk(f'r{rep}: retained heap at N=246016 equal across builds within 5 %', abs(a - b) <= 0.05 * a, f'{a} {b}')
    chk(f'r{rep}: block ratio 124/248 at N=246016 in 1.9..2.1', 1.9 <= g(txt[f'v124-tree-246016-r{rep}'], 'numBlocks') / g(txt[f'stock-tree-246016-r{rep}'], 'numBlocks') <= 2.1)
    for m in (1000, 100000, 1000000):
        chk(f'r{rep} M={m}: estimatedMemoryUse == 236 M in both builds', g(txt[f'stock-ctl-{m}-r{rep}'], 'estimatedMemoryUse') == 236 * m == g(txt[f'v124-ctl-{m}-r{rep}'], 'estimatedMemoryUse'))
if len(sys.argv) > 2:
    cr = sys.argv[2]
    summ = open(cr + '/summary.txt').read()

    def arm(lab):
        seg = summ.split(f'ARM {lab} start')[1].split(f'ARM {lab} STOPPED')[0]
        r = {}
        for ix in ('c_idx', 'u_idx'):
            m = re.search(rf"INDEX {ix} build (\w+) after \d+ s; files \[\('[^']+', (\d+)\)\]; temp-segment files seen (\d+)", seg)
            v = re.search(rf'VERIFY {ix}: count=(\d+) expected (\d+) (\w+)', seg)
            r[ix] = dict(done=m.group(1) == 'complete', bytes=int(m.group(2)), segs=int(m.group(3)), ok=v.group(3) == 'OK')
        return r
    A = {l: arm(l) for l in ('S-1M', 'S-500k', 'T124-1M', 'T124-500k', 'ctl-opt16')}
    chk('cluster: every index of every arm built and verified', all(x['done'] and x['ok'] for a in A.values() for x in a.values()))
    chk('cluster: c_idx bytes 1M / 500k in 1.8..2.2', 1.8 <= A['S-1M']['c_idx']['bytes'] / A['S-500k']['c_idx']['bytes'] <= 2.2, str(A['S-1M']['c_idx']['bytes'] / A['S-500k']['c_idx']['bytes']))
    exp = (math.ceil(1e6 / 248) + 17) * 4096
    chk('cluster: S-1M c_idx within 10 % of (4033 leaves + 17 interior) x 4096', abs(A['S-1M']['c_idx']['bytes'] - exp) <= 0.1 * exp, f"{A['S-1M']['c_idx']['bytes']} vs {exp}")
    chk('cluster: T124-1M c_idx / S-1M c_idx in 1.8..2.2', 1.8 <= A['T124-1M']['c_idx']['bytes'] / A['S-1M']['c_idx']['bytes'] <= 2.2, f"{A['T124-1M']['c_idx']['bytes'] / A['S-1M']['c_idx']['bytes']:.2f}")
    chk('cluster control: 16 MiB option writes more temp segment files than 1024', A['ctl-opt16']['c_idx']['segs'] > A['S-1M']['c_idx']['segs'], f"{A['ctl-opt16']['c_idx']['segs']} vs {A['S-1M']['c_idx']['segs']}")
print(f'SELFCHECK total FAIL={bad}')
sys.exit(1 if bad else 0)
