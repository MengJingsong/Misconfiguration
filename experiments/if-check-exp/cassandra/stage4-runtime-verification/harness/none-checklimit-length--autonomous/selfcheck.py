#!/usr/bin/env python3
"""Independent self-check for none-checklimit-length--autonomous (does not import analyze.py). usage: selfcheck.py <run dir>.
Recomputes arm medians from the raw 'rep' lines and re-evaluates the frozen predictions Q1-Q6 from the raw lines; scans the JVM logs."""
import glob, os, re, statistics, sys

d = sys.argv[1]
MiB = 1 << 20
res = []


def rec(name, ok, note=''):
    res.append((name, ok))
    print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + note if note else ''))


def fields(l):
    return {m.group(1): m.group(2) for m in re.finditer(r'(\w+)=(\S+)', l)}


raw = {p: open(os.path.join(d, f'test-{p}.out')).read().splitlines() for p in 'AB'}
reps, arms, other = {}, {}, {}
for p, lines in raw.items():
    for l in lines:
        f = fields(l)
        if ' rep ' in l:
            reps.setdefault((p, int(f['S']), f['arm']), []).append(int(f['med']))
        elif l.startswith('STAGE4 arm '):
            arms[(p, int(f['S']), f['arm'])] = f
        elif l.startswith('STAGE4 empty '):
            other[(p, int(f['S']), 'empty')] = f
        elif l.startswith('STAGE4 c1 '):
            other[(p, int(f['S']), 'c1')] = f
        elif l.startswith('STAGE4 retained '):
            other[(p, int(f['S']), 'ret' + f['arm'])] = f
Ss = sorted({k[1] for k in reps})
rec('five record sizes in both passes', len(Ss) == 5 and all((p, s, 'D') in reps for p in 'AB' for s in Ss), str(Ss))
med = {}
for k, v in reps.items():
    ok = len(v) == 5 and statistics.median(v) == int(arms[k]['repmedian'])
    med[k] = statistics.median(v)
    if not ok:
        rec(f'{k} recomputed median', False, str(v))
rec('every arm median recomputed from its 5 rep lines equals the arm line', all(len(v) == 5 and statistics.median(v) == int(arms[k]['repmedian']) for k, v in reps.items()))
for s in Ss:
    m = lambda a: med[('A', s, a)]
    rec(f'S={s} Q1 hits per call 3,3,3,2 (pass B)', [round(int(arms[('B', s, a)]['hits']) / int(arms[('B', s, a)]['calls']), 6) for a in ('F1', 'T1', 'N', 'D')] == [3, 3, 3, 2],
        str([(arms[('B', s, a)]['hits'], arms[('B', s, a)]['calls']) for a in ('F1', 'T1', 'N', 'D')]))
    af, at, an, ad = (arms[('A', s, a)] for a in ('F1', 'T1', 'N', 'D'))
    rec(f'S={s} Q2 outcomes', af['threw'] == '0' and af['lastCap'] == str(s) and an['lastCap'] == str(s) and at['threw'] == at['calls'] and at['lastMsg'] == 'Digest_mismatch_exception'
        and ad['lastNull'] == 'true', f"T threw {at['threw']}/{at['calls']}")
    rec(f'S={s} Q3 allocation bands', s + 16 <= m('F1') <= s + 2048 and abs(m('N') - m('F1')) <= 256 and s + 16 <= m('T1') <= s + 6144 and abs(m('T1') - m('F1')) <= 6144
        and m('D') <= 4096 and (s < 65536 or m('D') <= s // 8), f"F-S={m('F1') - s} T-S={m('T1') - s} N-F={m('N') - m('F1')} D={m('D')}")
    rec(f'S={s} T allocates at least S (the allocation precedes the throwing read)', m('T1') >= s)
    rec(f'S={s} Q4 noise', abs(m('F1') - m('F2')) <= 256 and abs(m('T1') - m('T2')) <= 1024 and int(other[('A', s, 'empty')]['e1']) <= 16 and int(other[('A', s, 'empty')]['e2']) <= 16)
    if s >= MiB:
        dF, dT = int(other[('A', s, 'retF')]['delta']), int(other[('A', s, 'retT')]['delta'])
        rec(f'S={s} Q5 retained', 0.9 * s <= dF <= 1.1 * s + MiB and abs(dT) <= 2 * MiB, f'F {dF} T {dT}; F held={other[("A", s, "retF")]["held"]} T held={other[("A", s, "retT")]["held"]}')
    c1 = int(other[('A', s, 'c1')]['median'])
    rec(f'S={s} Q6 C1 and D', s + 16 <= c1 <= s + 32 and m('D') < m('F1'), f'C1={c1} D={m("D")}')
rec('no MISMATCH lines', not any(l.endswith('MISMATCH') for p in raw for l in raw[p]))
errs = []
for fn in glob.glob(os.path.join(d, 'jvm-*.log')):
    for l in open(fn, errors='replace'):
        if re.search(r'Exception|Error|SEVERE|FATAL', l) and 'Byteman' not in l and 'WARN' not in l and 'STAGE4' not in l:
            errs.append((os.path.basename(fn), l.strip()[:120]))
rec('JVM logs contain no exception/error lines', not errs, str(errs[:3]))
print('SUMMARY', sum(1 for _, o in res if o), 'PASS,', sum(1 for _, o in res if not o), 'FAIL')
