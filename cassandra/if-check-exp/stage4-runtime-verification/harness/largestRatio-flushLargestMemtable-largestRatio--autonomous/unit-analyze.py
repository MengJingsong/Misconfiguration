#!/usr/bin/env python3
"""B2f / B2g (with amendments R1-R3, D1) checks for the unit tier. usage: unit-analyze.py <run dir>/unit
Reads each sub-directory's probe.txt (written by the test itself, -Dprobe.out) and the ant log (OutOfMemoryError lines,
junit result). Prints EXPECTED lines; a NO is recorded, not acted on."""
import os, re, sys

D = sys.argv[1]
MIB = 1 << 20
EXP = {'yes': 0, 'no': 0}


def expect(desc, cond):
    EXP['yes' if cond else 'no'] += 1
    print(f'EXPECTED: {desc} — {"yes" if cond else "NO"}')


def kv(line):
    return dict(re.findall(r'(\w+)=(\[[^\]]*\]|\S+)', line))


U3, U1, U1R, U2 = {}, None, None, []
OOM = {}
for sub in sorted(os.listdir(D)):
    p = f'{D}/{sub}/probe.txt'
    if not os.path.exists(p):
        continue
    OOM[sub] = len(re.findall(r'java.lang.OutOfMemoryError', open(f'{D}/{sub}/ant.log', errors='replace').read()))
    for l in open(p):
        if l.startswith('PROBE u3 '):
            k = kv(l)
            U3[(k['mutant'], int(k['L']) // MIB, k['variant'])] = k
        elif l.startswith('PROBE u1 '):
            U1 = kv(l)
        elif l.startswith('PROBE u1-result '):
            U1R = kv(l)
        elif l.startswith('PROBE u2 '):
            U2.append(kv(l))
print('OutOfMemoryError lines per JVM run:', OOM)
for k in sorted(U3):
    v = U3[k]
    print(f'u3 {k}: peak {int(v["peakUsed"]) / MIB:.2f} MiB = {float(v["peakRatio"]):.4f} L; rows {v["rowsDone"]}/{4 * int(v["rowsPerThread"])}; '
          f'timedOut {v["timedOutThreads"]}; switches {v["switchesTestTotal"]} (all CFS {v["switchesAllCfs"]}); mean flush '
          f'{int(v["meanFlushBytes"]) / MIB:.2f} MiB; blocked {v["blockedOnAllocating"]}; wall {v["wallMs"]} ms')
# U1
expect(f'U1: flushed CFS = the independent argmax ({U1R["changed"]} vs {U1R["argmax"]})', U1R['match'] == 'true')
expect(f'U1: argmax is T3 with ratio 6/128 +-30 % ({U1["argmaxRatio"]})',
       U1['argmax'].endswith(U1['T3']) and 0.7 * 6 / 128 <= float(U1['argmaxRatio']) <= 1.3 * 6 / 128)
expect('U1: T1 and T2 keep their memtables (only one CFS changed)', U1R['changed'].count(',') == 0)
expect(f'U1: Future returns true ({U1R["result"]})', U1R['result'] == 'true')
valid = [u for u in U2 if u['valid'] == 'true']
print(f'U2 attempts {len(U2)}, valid {len(valid)}')
expect('U2: a valid attempt exists (every ratio 0 at the call)', bool(valid))
if valid:
    expect(f'U2: the valid attempt returns false and no memtable switches ({valid[0]["result"]}, {valid[0]["changed"]})',
           valid[0]['result'] == 'false' and valid[0]['changed'] == '[]')
# U3 M-orig
for L in (32, 128):
    for var in ('skew', 'even'):
        v = U3.get(('M-orig', L, var))
        if v:
            r = float(v['peakRatio'])
            expect(f'M-orig L={L} {var}: peak/L in [0.33, 1.0] + 6 KiB ({r:.4f})', 0.33 <= r and int(v['peakUsed']) <= L * MIB + 6144)
    s, e = U3.get(('M-orig', L, 'skew')), U3.get(('M-orig', L, 'even'))
    if s and e:
        d = abs(float(s['peakRatio']) - float(e['peakRatio']))
        expect(f'M-orig L={L}: |peak/L skew - even| <= 0.10 ({float(s["peakRatio"]):.4f} vs {float(e["peakRatio"]):.4f}, diff {d:.4f})', d <= 0.10)
        rs = int(e['switchesTestTotal']) / max(1, int(s['switchesTestTotal']))
        expect(f'M-orig L={L}: S-even switches 2-4x S-skew ({e["switchesTestTotal"]}/{s["switchesTestTotal"]} = {rs:.2f}) with smaller flushes',
               2 <= rs <= 4 and int(e['meanFlushBytes']) < int(s['meanFlushBytes']))
for var in ('skew', 'even'):
    a, b = U3.get(('M-orig', 32, var)), U3.get(('M-orig', 128, var))
    if a and b:
        k = int(b['peakUsed']) / int(a['peakUsed'])
        expect(f'PC {var}: peakUsed L=128 / L=32 in [3, 5] ({k:.2f})', 3 <= k <= 5)
# mutants
for (m, L, var), v in sorted(U3.items()):
    if m == 'M-orig':
        continue
    expect(f'{m} L={L} {var}: peakUsed <= L + 1 MiB ({int(v["peakUsed"]) / MIB:.3f} MiB, samples over L {v["samplesOverL"]})',
           int(v['peakUsed']) <= L * MIB + MIB)
for L in (32, 128):
    v = U3.get(('M-first', L, 'even')), U3.get(('M-first', L, 'skew'))
    for x in v:
        if x:
            expect(f'M-first L={L} {x["variant"]}: switch counts include system or other small tables (all CFS {x["switchesAllCfs"]} > test {x["switchesTestTotal"]})',
                   int(x['switchesAllCfs']) > int(x['switchesTestTotal']))
n = U3.get(('M-never', 32, 'skew'))
if n:
    expect(f'M-never: plateau at <= L + overshoot ({int(n["peakUsed"])} <= {32 * MIB})', int(n['peakUsed']) <= 32 * MIB + 6144)
    expect(f'M-never: inserts time out ({n["timedOutThreads"]} threads)', int(n['timedOutThreads']) > 0)
    expect(f'M-never: blockedOnAllocating > 0 ({n["blockedOnAllocating"]})', int(n['blockedOnAllocating']) > 0)
    expect(f'M-never: never switched ({n["switchesAllCfs"]}) [R3 Invalid row excluded]', int(n['switchesAllCfs']) == 0)
expect(f'no variant reached L + 1 MiB (amended row 4, first clause)', all(int(v['peakUsed']) <= (k[1] + 1) * MIB for k, v in U3.items()))
expect(f'no test JVM ran out of heap (supplementary: real-heap gap, R3 last row) {OOM}', not any(OOM.values()))
print(f'EXPECTED totals: {EXP["yes"]} yes, {EXP["no"]} NO')
