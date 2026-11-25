#!/usr/bin/env python3
# Checks every ROW of the unit readings against B2f: counted == (k mod q)*r, dump == (k - k mod q)*r,
# dump grows only in steps of exactly M, counted == held bytes, counted + dump == k*r; control: counted == k*r.
import sys
r = 65536
rows = [l.strip().split(',') for l in open(sys.argv[1]) if l.startswith('ROW,')]
by = {}
for f in rows:
    by.setdefault(f[1], []).append(f)
for arm, rs in by.items():
    bad = 0; steps = set(); prev_d = 0
    for f in rs:
        M, k, c, d, de, h = int(f[2]), int(f[3]), int(f[4]), int(f[5]), int(f[6]), int(f[7])
        if arm in ('control',):
            exp_c, exp_d = k * r, -1
        elif arm.startswith('probe'):
            exp_c, exp_d = k * r, 0
        else:
            q = M // r
            exp_c, exp_d = (k % q) * r, (k - k % q) * r
        if c != exp_c or d != exp_d or c != h:
            bad += 1
            if bad <= 3: print('  mismatch', arm, k, c, exp_c, d, exp_d, h)
        if d > prev_d:
            steps.add(d - prev_d); prev_d = d
    print(f"{arm}: rows={len(rs)} mismatches={bad} dump-step sizes={sorted(steps)} last=(k={rs[-1][3]}, counted={rs[-1][4]}, dump={rs[-1][5]})")
