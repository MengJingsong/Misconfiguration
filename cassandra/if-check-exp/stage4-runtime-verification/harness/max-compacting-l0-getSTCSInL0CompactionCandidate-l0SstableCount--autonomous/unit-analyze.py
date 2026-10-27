#!/usr/bin/env python3
"""Unit tier analysis for max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.
usage: unit-analyze.py <readings.txt>  -> PASS/FAIL per prediction of B2f (amended 2026-10-26); a FAIL is a reading, not a harness error."""
import sys, collections
R = collections.OrderedDict()
for l in open(sys.argv[1]):
    p = l.rstrip('\n').split(' ', 3)
    if p[0] == 'R' and len(p) > 3: R[p[2]] = p[3]
MIB = 1048576; NS = (31, 32, 33, 64, 200); REPS = (1, 2, 3)
res = []
def chk(name, ok, detail=''):
    res.append((name, ok)); print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + detail if detail else ''))
def g(k): return R.get(k)
bad = collections.defaultdict(list)
def want(group, key, cond, desc):
    v = g(key)
    if v is None or not cond(v): bad[group].append(f'{key}={v} (want {desc})')
for table, mt in (('mt32', 32), ('mt8', 8)):
    for rep in REPS:
        for route in ('R0', 'R1', 'R2'):
            pre = f'{route}.{table}.rep{rep}'
            want('no error', pre + '.error', lambda v: v == 'none', 'none')
            want('R0 N=200 -> 200 L0 sstables, never refused', pre + '.N200.l0sstables', lambda v: v == '200', '200')
            for n in NS:
                want('L0 sstables overlap each other', f'{pre}.N{n}.l0allOverlapFirst', lambda v: v == 'true', 'true')
                want('L0 count N and unchanged by the read', f'{pre}.N{n}.flagfalse.l0count', lambda v, n=n: v == str(n), str(n))
                want('L0 count N and unchanged by the read', f'{pre}.N{n}.flagfalse.l0countBeforeRead', lambda v, n=n: v == str(n), str(n))
                want('L0 count N and unchanged by the read', f'{pre}.N{n}.flagtrue.l0count', lambda v, n=n: v == str(n), str(n))
                for flag in ('false', 'true'):
                    t = f'{pre}.N{n}.flag{flag}'
                    c = g(t + '.candidate')
                    if route == 'R0':
                        grp = 'R0: normal candidate, never STCS'
                        want(grp, t + '.candidate', lambda v: v == 'non-null', 'non-null')
                        want(grp, t + '.stcs', lambda v: v == 'false', 'false')
                        want(grp, t + '.maxSSTableBytes', lambda v: v == str(MIB), str(MIB))
                        want(grp, t + '.size', lambda v, mt=mt: 2 <= int(v) <= mt, f'2..{mt}')
                    elif route == 'R1':
                        if flag == 'false' and n >= 33:
                            grp = 'R1 N>=33 flag false: STCS candidate of max_threshold'
                            want(grp, t + '.stcs', lambda v: v == 'true', 'true')
                            want(grp, t + '.size', lambda v, mt=mt: v == str(mt), str(mt))
                            want(grp, t + '.level', lambda v: v == '0', '0')
                            want(grp, t + '.inputLevels', lambda v: v == '0..0', '0..0')
                        else:
                            grp = 'R1 N<=32 or flag true: normal L1->L2 candidate'
                            want(grp, t + '.stcs', lambda v: v == 'false', 'false')
                            want(grp, t + '.level', lambda v: v == '2', '2')
                            want(grp, t + '.inputLevels', lambda v: v == '1..1', '1..1')
                    else:
                        if flag == 'false' and n >= 33:
                            grp = 'R2 N>=33 flag false: STCS candidate of max_threshold, not the held one'
                            want(grp, t + '.stcs', lambda v: v == 'true', 'true')
                            want(grp, t + '.size', lambda v, mt=mt: v == str(mt), str(mt))
                            want(grp, t + '.containsHeld', lambda v: v == 'false', 'false')
                        else:
                            grp = 'R2 N<=32 or flag true: null'
                            want(grp, t + '.candidate', lambda v: v == 'null', 'null')
            if route == 'R1':
                want('R1 setup: 30 L1 sstables at about 3x target', pre + '.L1count', lambda v: v == '30', '30')
                want('R1 setup: 30 L1 sstables at about 3x target', pre + '.L1bytes', lambda v, pre=pre: 2.7 <= int(v) / int(g(pre + '.L1target')) <= 3.5, '2.7-3.5 x target')
            if route == 'R2':
                want('R2 setup: exactly one sstable held', pre + '.heldNotNull', lambda v: v == 'true', 'true')
                want('R2 setup: exactly one sstable held', pre + '.compactingCount', lambda v: v == '1', '1')
for grp, items in bad.items(): pass
allg = sorted({k for k in bad})
groups = ['no error', 'R0 N=200 -> 200 L0 sstables, never refused', 'L0 sstables overlap each other', 'L0 count N and unchanged by the read',
          'R0: normal candidate, never STCS', 'R1 N>=33 flag false: STCS candidate of max_threshold', 'R1 N<=32 or flag true: normal L1->L2 candidate',
          'R2 N>=33 flag false: STCS candidate of max_threshold, not the held one', 'R2 N<=32 or flag true: null',
          'R1 setup: 30 L1 sstables at about 3x target', 'R2 setup: exactly one sstable held']
for gname in groups: chk(gname, not bad.get(gname), '; '.join(bad[gname][:4]) if bad.get(gname) else 'all reps, both tables')
# execute step
eb = []
for table, mt in (('mt32', 32), ('mt8', 8)):
    for n in (33, 64):
        for rep in REPS:
            pre = f'exec.{table}.N{n}.rep{rep}'
            try:
                ok = g(pre + '.taskNonNull') == 'true' and int(g(pre + '.l0before')) == n and int(g(pre + '.l0after')) == n - (mt - 1) and int(g(pre + '.totalAfter')) == int(g(pre + '.totalBefore')) - (mt - 1)
            except Exception: ok = False
            if not ok: eb.append(pre)
chk('execute: one STCS task takes the L0 count from N to N-(max_threshold-1)', not eb, str(eb[:4]) if eb else 'N 33, 64 x 2 tables x 3 reps')
# positive control
cb = []
for rep in REPS:
    pre = f'ctl.rep{rep}'
    try:
        t = int(g(pre + '.L1target')); b0 = int(g(pre + '.L1before')); b1 = int(g(pre + '.L1after'))
        ok = b0 > 2.5 * t and b1 <= t * 1.001 and int(g(pre + '.tasks')) >= 1 and int(g(pre + '.L2after')) > 0 and g(pre + '.firstCandidate').startswith('level=2') and g(pre + '.firstCandidate').endswith('inputLevel=1') and g(pre + '.bytesAfterTruncate') == '0'
    except Exception: ok = False
    if not ok: cb.append(pre)
chk('positive control: L1 at 3x target returns to <= 1.001 x target by executing L1->L2 candidates; truncate gives 0', not cb, str(cb) if cb else '3 reps')
for rep in REPS:
    pre = f'ctl.rep{rep}'
    print('INFO', pre, 'L1 before/after/target', g(pre + '.L1before'), g(pre + '.L1after'), g(pre + '.L1target'), 'tasks', g(pre + '.tasks'), 'L2after', g(pre + '.L2after'))
fails = [r for r in res if not r[1]]
print('ALL PREDICTIONS PASS' if not fails else f'{len(fails)} PREDICTION GROUP(S) FAIL')
