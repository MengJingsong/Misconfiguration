#!/usr/bin/env python3
"""Analysis of none-checklimit-length--autonomous (unit tier, B2 as amended 2026-10-29). usage: analyze.py <run dir>
Reads test-A.out and test-B.out; prints the readings and one EXPECTED line per frozen prediction Q1-Q6."""
import os, sys

d = sys.argv[1]
MiB = 1 << 20


def kv(line):
    return dict(x.split('=', 1) for x in line.split()[2:] if '=' in x)


def load(fn):
    return [l.rstrip('\n') for l in open(os.path.join(d, fn)) if l.startswith('STAGE4 ')]


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
        if p[1] in ('arm', 'empty', 'c1', 'branch', 'retained'):
            k = kv(l)
            s = int(k['S'])
            if p[1] == 'arm':
                r.setdefault(s, {}).setdefault('arms', {})[k['arm']] = k
            elif p[1] == 'retained':
                r.setdefault(s, {}).setdefault('ret', {})[k['arm']] = k
            else:
                r.setdefault(s, {})[p[1]] = k
    return r


a, b = collect(A), collect(B)
print('S | F1 | T1 | F2 | T2 | N | D | T1-F1 | c1 | retained dF / dT | hits/call F,T,N,D (pass B) | T outcomes')
for s in sorted(a):
    ar = a[s]['arms']; bb = b[s]['arms']
    m = {k: int(ar[k]['repmedian']) for k in ar}
    print(f"{s} | {m['F1']} | {m['T1']} | {m['F2']} | {m['T2']} | {m['N']} | {m['D']} | {m['T1'] - m['F1']} | {a[s]['c1']['median']} | "
          f"{a[s]['ret']['F']['delta']} / {a[s]['ret']['T']['delta']} | "
          f"{bb['F1']['hitsPerCall']},{bb['T1']['hitsPerCall']},{bb['N']['hitsPerCall']},{bb['D']['hitsPerCall']} | threw={ar['T1']['threw']}/{ar['T1']['calls']} {ar['T1']['lastMsg']}")
for s in sorted(a):
    ar = a[s]['arms']; bb = b[s]['arms']
    m = {k: int(ar[k]['repmedian']) for k in ar}
    expect(f'S={s} Q1 pass B hits per call F,T,N,D = 3,3,3,2 ({bb["F1"]["hitsPerCall"]},{bb["T1"]["hitsPerCall"]},{bb["N"]["hitsPerCall"]},{bb["D"]["hitsPerCall"]})',
           [float(bb[k]['hitsPerCall']) for k in ('F1', 'T1', 'N', 'D')] == [3.0, 3.0, 3.0, 2.0])
    expect(f'S={s} Q2 outcomes: F,N capacity S; T threw every call with "Digest_mismatch_exception"; D null',
           ar['F1']['lastCap'] == str(s) and ar['N']['lastCap'] == str(s) and ar['T1']['threw'] == ar['T1']['calls'] and ar['T1']['lastMsg'] == 'Digest_mismatch_exception'
           and ar['F1']['threw'] == '0' and ar['D']['lastNull'] == 'true')
    expect(f'S={s} Q3 F in [S+16,S+2048] ({m["F1"] - s}); |N-F|<=256 ({abs(m["N"] - m["F1"])}); T in [S+16,S+6144] ({m["T1"] - s}); |T-F|<=6144 ({abs(m["T1"] - m["F1"])}); D<=4096 ({m["D"]})'
           + (f' and D<=S/8 ({m["D"]} vs {s // 8})' if s >= 65536 else ''),
           s + 16 <= m['F1'] <= s + 2048 and abs(m['N'] - m['F1']) <= 256 and s + 16 <= m['T1'] <= s + 6144 and abs(m['T1'] - m['F1']) <= 6144 and m['D'] <= 4096 and (s < 65536 or m['D'] <= s // 8))
    e = a[s]['empty']
    expect(f'S={s} Q4 |F1-F2|<=256 ({abs(m["F1"] - m["F2"])}), |T1-T2|<=1024 ({abs(m["T1"] - m["T2"])}), EMPTY<=16 ({e["e1"]},{e["e2"]})',
           abs(m['F1'] - m['F2']) <= 256 and abs(m['T1'] - m['T2']) <= 1024 and int(e['e1']) <= 16 and int(e['e2']) <= 16)
    if s >= MiB:
        dF, dT = int(a[s]['ret']['F']['delta']), int(a[s]['ret']['T']['delta'])
        expect(f'S={s} Q5 retained F in [0.9S, 1.1S+1MiB] ({dF}), T within 2 MiB ({dT})', 0.9 * s <= dF <= 1.1 * s + MiB and abs(dT) <= 2 * MiB)
    c1 = int(a[s]['c1']['median'])
    expect(f'S={s} Q6 C1 in [S+16,S+32] ({c1}); D moves (D {m["D"]} << F {m["F1"]})', s + 16 <= c1 <= s + 32 and m['D'] < m['F1'])
mm = sum(1 for l in A + B if l.endswith('MISMATCH'))
expect(f'no MISMATCH check lines ({mm})', mm == 0)
print('ALL EXPECTED HOLD' if ok_all else 'SOME EXPECTED DO NOT HOLD')
