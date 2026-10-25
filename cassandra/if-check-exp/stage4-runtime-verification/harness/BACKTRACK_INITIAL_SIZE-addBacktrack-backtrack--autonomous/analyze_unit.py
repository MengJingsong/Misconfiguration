#!/usr/bin/env python3
"""Checks the frozen unit-tier predictions (case file B2i.6) against <outdir>/T*/results.csv. Usage: analyze_unit.py <outdir>"""
import sys, glob, os, csv
out = sys.argv[1]
EL = {  # (shape, D) -> (E, L)
 **{('chain', d): (0, 48) for d in (8, 64, 1024, 65535)},
 ('sparse', 8): (8, 48), ('sparse', 64): (64, 192), ('sparse', 1024): (1024, 3072), ('sparse', 65535): (65535, 196608),
 ('split', 8): (24, 96), ('split', 64): (192, 768), ('split', 1024): (3072, 12288), ('split', 65535): (196605, 786432),
}
npass = nfail = 0
def chk(ok, msg):
    global npass, nfail
    if ok: npass += 1
    else: nfail += 1
    print(('PASS ' if ok else 'FAIL ') + msg)
seen = {}
for f in sorted(glob.glob(os.path.join(out, 'T*', 'results.csv'))):
    T = int(os.path.basename(os.path.dirname(f))[1:])
    rows = [r for r in csv.reader(open(f)) if r and r[0] != 'arm']
    names = [(r[0], r[1]) for r in rows]
    chk(len(rows) == len(set(names)), 'T%d: arm names unique (%d rows)' % (T, len(rows)))
    for r in rows:
        arm, buf = r[0], r[1]; tag = 'T%d %s %s' % (T, arm, buf)
        if arm == 'reuse':
            chk(r[7] == '48' and r[9] == '192', tag + ': fresh cursor L=48 (got %s), reused cursor keeps L=192 (got %s)' % (r[7], r[9])); continue
        if arm == 'thr':
            thr, = [r[11].split(';')[1]]; Tm = int(r[11].split(';')[0])
            f0, f1, f2 = r[12].split(';'); p1, p2 = [int(x) for x in r[13].split(';')]; o1, o2 = [int(x) for x in r[14].split(';')]
            chk(Tm == T and int(thr) == T << 20, tag + ': threshold == T*2^20 (T=%d, thr=%s)' % (Tm, thr))
            chk((f0, f1, f2) == ('false', 'false', 'true'), tag + ': flags false;false;true (got %s)' % r[12])
            chk(p1 >= (T - 1) << 20 and p2 >= T << 20 and o1 == p1 and o2 == p2, tag + ': sizeOffHeap == allocated pos (%d,%d)' % (o1, o2))
            chk(r[8] == '1024' and r[9] == '3072' and r[6] == '1025', tag + ': comb D=1024 in same trie E=1024 L=3072 (got E=%s L=%s)' % (r[8], r[9]))
            continue
        shape, D, F = r[2], int(r[3]), int(r[4])
        chk(r[6] == r[5], tag + ': content nodes visited %s == keys %s (known answer)' % (r[6], r[5]))
        chk(r[7] == '48', tag + ': fresh L0 == 48 (got %s)' % r[7])
        chk(r[11] == r[12] and r[13] == r[14], tag + ': sizeOnHeap/sizeOffHeap unchanged by cursor (%s->%s, %s->%s)' % (r[11], r[12], r[13], r[14]))
        if arm.startswith('fill_'): e, l = 64, 192
        elif arm == 'put1024': e, l = 1024, 3072
        else: e, l = EL[(shape, D)]
        chk(int(r[8]) == e and int(r[9]) == l, tag + ': E=%s L=%s (predicted E=%d L=%d)' % (r[8], r[9], e, l))
        chk(int(r[10]) == 16 + 4 * int(r[9]), tag + ': array bytes = 16+4L')
        seen.setdefault(arm, {})[(T, buf)] = (r[8], r[9])
for arm, d in seen.items():
    chk(len(set(d.values())) == 1, 'arm %s: (E,L) identical across ON/OFF_HEAP and all T JVMs: %s' % (arm, sorted(set(d.values()))))
print('SUMMARY pass=%d fail=%d' % (npass, nfail))
