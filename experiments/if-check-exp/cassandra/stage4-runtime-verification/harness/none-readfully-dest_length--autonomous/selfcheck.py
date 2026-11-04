#!/usr/bin/env python3
"""Independent self-check for none-readfully-dest_length--autonomous / none-read-count--autonomous (does not import or reuse analyze.py).
usage: selfcheck.py <run dir>. Recomputes every arm median from the raw 'rep' lines (median of the five repetition medians), re-evaluates the
frozen predictions P1-P7 from the raw lines, and reports PASS/FAIL per item plus NOTE lines for misses; also scans the JVM logs for errors."""
import glob, os, re, statistics, sys

d = sys.argv[1]
MiB = 1 << 20
res = []


def rec(name, ok, note=''):
    res.append((name, ok))
    print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + note if note else ''))


def fields(l):
    return {m.group(1): m.group(2) for m in re.finditer(r'(\w+)=(\S+)', l)}


raw = {'A': open(os.path.join(d, 'test-A.out')).read().splitlines(), 'B': open(os.path.join(d, 'test-B.out')).read().splitlines()}
reps = {}   # (pass, N, arm) -> [rep medians]
armline = {}
other = {}
for p, lines in raw.items():
    for l in lines:
        f = fields(l)
        if ' rep ' in l:
            reps.setdefault((p, int(f['N']), f['arm']), []).append(int(f['med']))
        elif l.startswith('STAGE4 arm '):
            armline[(p, int(f['N']), f['arm'])] = f
        elif l.startswith('STAGE4 empty '):
            other[(p, int(f['N']), 'empty')] = f
        elif l.startswith('STAGE4 c1 '):
            other[(p, int(f['N']), 'c1')] = f
        elif l.startswith('STAGE4 c2 '):
            other[(p, int(f['N']), 'c2')] = f
        elif l.startswith('STAGE4 retained '):
            other[(p, int(f['N']), 'ret' + f['arm'])] = f
Ns = sorted({k[1] for k in reps})
rec('six operand values present in both passes', len(Ns) == 6 and all((p, n, 'T1') in reps for p in 'AB' for n in Ns), str(Ns))
med = {}
for (p, n, arm), v in reps.items():
    rec(f'{p} N={n} {arm}: 5 reps, recomputed median equals the arm line', len(v) == 5 and statistics.median(v) == int(armline[(p, n, arm)]['repmedian']), f'{v}')
    med[(p, n, arm)] = statistics.median(v)
for n in Ns:
    F, T = med[('A', n, 'F1')], med[('A', n, 'T1')]
    rec(f'N={n} P1 hits (pass B): F 0/0, T = calls', armline[('B', n, 'F1')]['hits'] == '0' and armline[('B', n, 'F2')]['hits'] == '0'
        and armline[('B', n, 'T1')]['hits'] == armline[('B', n, 'T1')]['calls'] and armline[('B', n, 'T2')]['hits'] == armline[('B', n, 'T2')]['calls'],
        f"T1 {armline[('B', n, 'T1')]['hits']}/{armline[('B', n, 'T1')]['calls']}")
    rec(f'N={n} P2 F <= 512', F <= 512, str(F))
    ok3 = 4 * n + 16 <= T - F <= 4 * n + 640
    rec(f'N={n} P3 T-F in [4N+16,4N+640]', ok3, f'T-F={T - F}, excess over 4N = {T - F - 4 * n}, regions crossed ~ {max(1, 4 * n // 65536)}')
    if not ok3:
        print(f'NOTE N={n}: frozen P3 band missed; T-F-4N = {T - F - 4 * n} bytes (about {(T - F - 4 * n) / max(1, 4 * n // 65536):.0f} per 64 KiB region crossed)')
    rec(f'N={n} P4 noise', abs(F - med[('A', n, 'F2')]) <= 32 and abs(T - med[('A', n, 'T2')]) <= 64 and int(other[('A', n, 'empty')]['e1']) <= 16 and int(other[('A', n, 'empty')]['e2']) <= 16)
    rec(f'N={n} P6 retained within 2 MiB', abs(int(other[('A', n, 'retF')]['delta'])) <= 2 * MiB and abs(int(other[('A', n, 'retT')]['delta'])) <= 2 * MiB,
        f"F {other[('A', n, 'retF')]['delta']} T {other[('A', n, 'retT')]['delta']}")
    c1 = int(other[('A', n, 'c1')]['median']); c2 = int(other[('A', n, 'c2')]['delta'])
    rec(f'N={n} P7 C1 in [4N+16,4N+32]', 4 * n + 16 <= c1 <= 4 * n + 32, str(c1))
    ok7 = c2 >= 90 * MiB
    rec(f'N={n} P7 C2 >= 90 MiB', ok7, f"{c2} with {other[('A', n, 'c2')]['arrays']} arrays")
    if not ok7:
        print(f"NOTE N={n}: the C2 design capped the array count at 250000, so the target of 100 MiB was unreachable ({other[('A', n, 'c2')]['arrays']} arrays x {16 + 4 * n} B); the control still moved by {c2 / MiB:.1f} MiB, 18x the 2 MiB band")
fs = [med[('A', n, 'F1')] for n in Ns]
rec('P2 spread of F across N <= 64', max(fs) - min(fs) <= 64, str(max(fs) - min(fs)))
rec('P5 no MISMATCH lines, all arms data=ok', not any(l.endswith('MISMATCH') for p in raw for l in raw[p]) and all(f['data'] == 'ok' for f in armline.values()))
errs = []
for fn in glob.glob(os.path.join(d, 'jvm-*.log')):
    for l in open(fn, errors='replace'):
        if re.search(r'Exception|Error|SEVERE|FATAL', l) and 'Byteman' not in l and 'WARN' not in l and 'STAGE4' not in l:
            errs.append((os.path.basename(fn), l.strip()[:120]))
rec('JVM logs contain no exception/error lines', not errs, str(errs[:3]))
print('SUMMARY', sum(1 for _, o in res if o), 'PASS,', sum(1 for _, o in res if not o), 'FAIL')
