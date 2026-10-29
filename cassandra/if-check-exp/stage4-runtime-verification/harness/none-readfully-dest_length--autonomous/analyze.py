#!/usr/bin/env python3
"""Analysis of none-readfully-dest_length--autonomous / none-read-count--autonomous (unit tier, B2 as amended 2026-10-29).
usage: analyze.py <run dir>   (reads test-A.out and test-B.out). Prints the readings and one EXPECTED line per frozen prediction P1-P7.
It prints; the AI matches the readings to a row of the amended B2g in the results file."""
import re, sys, os

d = sys.argv[1]
MiB = 1 << 20


def kv(line):
    return dict(x.split('=', 1) for x in line.split()[2:] if '=' in x)


def load(fn):
    rows = []
    for l in open(os.path.join(d, fn)):
        if l.startswith('STAGE4 '):
            rows.append(l.rstrip('\n'))
    return rows


A, B = load('test-A.out'), load('test-B.out')
ok_all = True


def expect(desc, cond):
    global ok_all
    ok_all &= bool(cond)
    print(f'EXPECTED: {desc} - {"yes" if cond else "NO"}')


def collect(rows):
    r = {}
    for l in rows:
        p = l.split()
        if p[1] == 'arm':
            k = kv(l)
            r.setdefault(int(k['N']), {}).setdefault('arms', {})[k['arm']] = k
        elif p[1] in ('empty', 'c1', 'branch'):
            k = kv(l)
            r.setdefault(int(k['N']), {})[p[1]] = k
        elif p[1] in ('retained', 'c2'):
            k = kv(l)
            r.setdefault(int(k['N']), {}).setdefault(p[1], {})[k.get('arm', 'c2')] = k
    return r


a, b = collect(A), collect(B)
Ns = sorted(a)
print('N | F1 | F2 | T1 | T2 | T1-F1 | 4N | c1 | retained dF / dT | c2 delta | pass B hits F1/T1 (calls)')
for n in Ns:
    x = a[n]; arms = x['arms']
    f1, f2, t1, t2 = (int(arms[k]['repmedian']) for k in ('F1', 'F2', 'T1', 'T2'))
    rt = x.get('retained', {})
    bb = b.get(n, {}).get('arms', {})
    print(f"{n} | {f1} | {f2} | {t1} | {t2} | {t1 - f1} | {4 * n} | {x['c1']['median']} | "
          f"{rt.get('F', {}).get('delta')} / {rt.get('T', {}).get('delta')} | {x['c2']['c2']['delta']} | "
          f"{bb.get('F1', {}).get('hits')}/{bb.get('T1', {}).get('hits')} ({bb.get('T1', {}).get('calls')})")

fs = []
for n in Ns:
    arms = a[n]['arms']; bb = b[n]['arms']
    f1, f2, t1, t2 = (int(arms[k]['repmedian']) for k in ('F1', 'F2', 'T1', 'T2'))
    fs.append(f1)
    expect(f'N={n} P1 pass B: F1/F2 hits 0, T1/T2 hits = calls ({bb["T1"]["hits"]}/{bb["T1"]["calls"]}, {bb["T2"]["hits"]}/{bb["T2"]["calls"]})',
           bb['F1']['hits'] == '0' and bb['F2']['hits'] == '0' and bb['T1']['hits'] == bb['T1']['calls'] and bb['T2']['hits'] == bb['T2']['calls'])
    expect(f'N={n} P2 F1 <= 512 ({f1})', f1 <= 512)
    expect(f'N={n} P3 T1-F1 in [4N+16, 4N+640] ({t1 - f1} vs [{4 * n + 16}, {4 * n + 640}])', 4 * n + 16 <= t1 - f1 <= 4 * n + 640)
    e = a[n]['empty']
    expect(f'N={n} P4 |F1-F2|<=32 ({abs(f1 - f2)}), |T1-T2|<=64 ({abs(t1 - t2)}), EMPTY<=16 ({e["e1"]},{e["e2"]})',
           abs(f1 - f2) <= 32 and abs(t1 - t2) <= 64 and int(e['e1']) <= 16 and int(e['e2']) <= 16)
    if n >= 16384:
        sp = max(abs(f1 - f2), abs(t1 - t2), 1)
        expect(f'N={n} P4 (T-F) >= 10 x larger spread ({t1 - f1} vs {10 * sp})', (t1 - f1) >= 10 * sp)
    rt = a[n]['retained']
    expect(f'N={n} P6 retained |dF|,|dT| <= 2 MiB ({rt["F"]["delta"]}, {rt["T"]["delta"]})', abs(int(rt['F']['delta'])) <= 2 * MiB and abs(int(rt['T']['delta'])) <= 2 * MiB)
    c1 = int(a[n]['c1']['median'])
    expect(f'N={n} P7 C1 in [4N+16, 4N+32] ({c1}); C2 delta >= 90 MiB ({a[n]["c2"]["c2"]["delta"]})',
           4 * n + 16 <= c1 <= 4 * n + 32 and int(a[n]['c2']['c2']['delta']) >= 90 * MiB)
expect(f'P2 spread of F1 across N <= 64 ({max(fs) - min(fs)})', max(fs) - min(fs) <= 64)
mm = sum(1 for l in A + B if l.endswith('MISMATCH'))
expect(f'P5 data and file-pointer checks: no MISMATCH lines ({mm}), every arm data=ok',
       mm == 0 and all('data=ok' in l for l in A + B if l.startswith('STAGE4 arm ')))
print('ALL EXPECTED HOLD' if ok_all else 'SOME EXPECTED DO NOT HOLD')
