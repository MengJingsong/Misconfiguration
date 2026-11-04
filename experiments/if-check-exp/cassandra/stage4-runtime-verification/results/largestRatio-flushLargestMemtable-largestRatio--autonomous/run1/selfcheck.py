#!/usr/bin/env python3
"""Self-check (stage-4 step 4) of run 1, written after the conclusion. It does not read analysis.txt, flushes.txt or the
analysis scripts' output. usage: selfcheck.py <run dir>   (e.g. ~/stage4-logs/lrt/run1)
Unit: re-reads each PROBE line from the ant log (the System.out path, a different file from probe.txt) and compares it
with probe.txt; M-never's JVM was stopped by the junit timeout before its log was flushed, so only probe.txt holds it.
Cluster: re-reads system.log between arm.json's offsets (selection lines and flush reasons), jmx.csv, gc.log Full-GC
lines and the stress outputs. Prints 'ok' / 'FAIL' per check of the conclusion."""
import json, os, re, statistics, sys

R = sys.argv[1]
MIB = 1 << 20
C = {'ok': 0, 'FAIL': 0}


def chk(desc, cond):
    k = 'ok' if cond else 'FAIL'
    C[k] += 1
    print(f'{k}: {desc}')


def kv(l):
    return dict(re.findall(r'(\w+)=(\[[^\]]*\]|\S+)', l))


# ---------------- unit
U = {}
for sub in sorted(os.listdir(R + '/unit')):
    d = f'{R}/unit/{sub}'
    if not os.path.isdir(d):
        continue
    pf = [l.strip() for l in open(d + '/probe.txt') if l.startswith('PROBE')]
    al = [m.group(1).strip() for l in open(d + '/ant.log', errors='replace')
          for m in [re.search(r'SubstituteLogger\.java:\d+ - (PROBE .*)$', l)] if m]
    if al:
        chk(f'unit {sub}: ant-log PROBE lines equal probe.txt ({len(al)} vs {len(pf)})', al == pf)
    for l in pf:
        if l.startswith('PROBE u3 '):
            k = kv(l)
            U[(k['mutant'], int(k['L']) // MIB, k['variant'])] = k
        if l.startswith('PROBE u1-result'):
            k = kv(l)
            chk(f'unit U1: changed {k["changed"]} = argmax {k["argmax"]}, result {k["result"]}',
                k['changed'] == f'[{k["argmax"]}]' and k['result'] == 'true')
        if l.startswith('PROBE u2 ') and 'valid=true' in l:
            k = kv(l)
            chk(f'unit U2 valid attempt {k["attempt"]}: result false, nothing changed', k['result'] == 'false' and k['changed'] == '[]')
pr = lambda m, L, v: float(U[(m, L, v)]['peakRatio'])
pk = lambda m, L, v: int(U[(m, L, v)]['peakUsed'])
chk(f'unit M-orig L=128: skew {pr("M-orig", 128, "skew")} - even {pr("M-orig", 128, "even")} > 0.10 (the Refuted reading)',
    pr('M-orig', 128, 'skew') - pr('M-orig', 128, 'even') > 0.10)
chk(f'unit M-orig L=32: |skew - even| <= 0.10', abs(pr('M-orig', 32, 'skew') - pr('M-orig', 32, 'even')) <= 0.10)
chk('unit: every variant peakUsed <= L (no sample over L)', all(int(v['peakUsed']) <= k[1] * MIB and v['samplesOverL'] == '0' for k, v in U.items()))
for v in ('skew', 'even'):
    r = pk('M-orig', 128, v) / pk('M-orig', 32, v)
    chk(f'unit PC {v}: L128/L32 = {r:.2f} in [3, 5]', 3 <= r <= 5)
n = U[('M-never', 32, 'skew')]
chk(f'unit M-never: peak {n["peakUsed"]} within 1 KiB of L, 4 threads timed out, 0 switches',
    32 * MIB - 1024 <= int(n['peakUsed']) <= 32 * MIB and n['timedOutThreads'] == '4' and n['switchesAllCfs'] == '0')
fe = U[('M-first', 128, 'even')]
oom = len(re.findall('java.lang.OutOfMemoryError', open(R + '/unit/first-L128/ant.log', errors='replace').read()))
chk(f'unit M-first L=128 even: OOM lines {oom} > 0 with peakUsed {int(fe["peakUsed"]) / MIB:.1f} MiB <= 128 and rows {fe["rowsDone"]} < 208000',
    oom > 0 and int(fe['peakUsed']) <= 128 * MIB and int(fe['rowsDone']) < 208000)
gl = open(R + '/unit/first-L128/gc.log').read()
fulls = [int(b) for a, b in re.findall(r'Pause Full \(Allocation Failure\) (\d+)M->(\d+)M', gl)]
chk(f'unit M-first L=128: a Full GC left >= 900 MiB live in the 1 GiB JVM (max after Full GC {max(fulls) if fulls else None} MiB)',
    fulls and max(fulls) >= 900)
for lab in ('orig-L128', 'orig-L32'):
    fl = [int(b) for a, b in re.findall(r'Pause Full \([^)]*\) (\d+)M->(\d+)M', open(f'{R}/unit/{lab}/gc.log').read())]
    print(f'  info: {lab} Full GC after-values {fl}')

# ---------------- cluster
A = {}
for arm in ('L256-skew', 'L256-even', 'L1024-skew', 'L1024-even', 'never'):
    d = f'{R}/cluster/{arm}'
    a = json.load(open(d + '/arm.json'))
    raw = open(d + '/system.log', 'rb').read()[a['syslog_offset']:a['syslog_end_offset']].decode(errors='replace')
    sel = [(float(x), float(y)) for x, y in re.findall(r'Flushing largest .*? Used total: ([\d.]+)/[\d.]+, .*? this: ([\d.]+)/', raw)]
    reasons = re.findall(r'Enqueuing flush of (\w+)\.\w+, Reason: (\w+)', raw)
    t0, t1 = a['stress_start_ms'], a['stress_end_ms']
    allmem = [int(p[1]) for p in (l.strip().split(',') for l in open(d + '/jmx.csv')) if len(p) == 6 and p[1].isdigit() and t0 <= int(p[0]) <= t1]
    A[arm] = dict(L=a['L_MiB'] * MIB, sel=sel, reasons=reasons, allmem=max(allmem), n=len(allmem))
    us = [x for x, _ in sel]
    print(f'  info: {arm}: {len(sel)} selections, a max {max(us) if us else None} median {statistics.median(us) if us else None}, '
          f'g median {statistics.median([y for _, y in sel]) if sel else None}; AllMem peak {max(allmem) / MIB:.1f} MiB over {len(allmem)} samples; '
          f'stress-table flush reasons {sorted(set(r for k, r in reasons if k.startswith("ks")))}')
for arm in ('L256-skew', 'L256-even', 'L1024-skew', 'L1024-even'):
    x = A[arm]
    chk(f'cluster {arm}: selections > 0, every a <= 1.02, AllMem peak <= L, stress-table flushes all MEMTABLE_LIMIT',
        x['sel'] and max(u for u, _ in x['sel']) <= 1.02 and x['allmem'] <= x['L'] and
        all(r == 'MEMTABLE_LIMIT' for k, r in x['reasons'] if k.startswith('ks')))
for L in (256, 1024):
    s, e = A[f'L{L}-skew'], A[f'L{L}-even']
    ms, me = max(u for u, _ in s['sel']), max(u for u, _ in e['sel'])
    ds = statistics.median([u for u, _ in s['sel']]); de = statistics.median([u for u, _ in e['sel']])
    chk(f'cluster L={L}: max a skew {ms} vs even {me} differ by > 0.10 and medians {ds} vs {de} by > 0.10 (the Refuted reading)',
        me - ms > 0.10 and de - ds > 0.10)
    chk(f'cluster L={L}: AllMem peak/L skew {s["allmem"] / s["L"]:.3f} vs even {e["allmem"] / e["L"]:.3f} within 0.10',
        abs(s['allmem'] / s['L'] - e['allmem'] / e['L']) <= 0.10)
for w in ('skew', 'even'):
    r = A[f'L1024-{w}']['allmem'] / A[f'L256-{w}']['allmem']
    chk(f'cluster PC {w}: AllMem peak L1024/L256 = {r:.2f} in [3, 5]', 3 <= r <= 5)
nv = A['never']
chk(f'cluster never: 0 selections, 0 MEMTABLE_LIMIT flushes, AllMem peak {nv["allmem"] / MIB:.2f} MiB in [0.9 L, 1.02 L]',
    not nv['sel'] and not any(r == 'MEMTABLE_LIMIT' for _, r in nv['reasons']) and 0.9 * nv['L'] <= nv['allmem'] <= 1.02 * nv['L'])
st = open(R + '/cluster/never/stress-ks1.out', errors='replace').read()
chk(f'cluster never: stress output holds timeouts ({len(re.findall("WriteTimeout|timed out", st))} lines) and no OOM in system.log',
    re.search('WriteTimeout|timed out', st) is not None and 'java.lang.OutOfMemoryError' not in open(R + '/cluster/never/system.log', errors='replace').read())
for arm in ('L256-skew', 'L256-even', 'L1024-skew', 'L1024-even'):
    fl = re.findall(r'Pause Full \([^)]*\) (\d+)M->(\d+)M', open(f'{R}/cluster/{arm}/gc.log').read())
    print(f'  info: {arm} Full GC (before->after MiB): {fl}')
print(f'selfcheck totals: {C["ok"]} ok, {C["FAIL"]} FAIL')
