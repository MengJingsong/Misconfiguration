#!/usr/bin/env python3 -I
"""Unit-tier analyzer for DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous (B2f/B2g as amended B2i).
Usage: analyze_unit.py <raw-dir>. Reads arms.txt, calls-*.csv, files-*.csv. Prints RESULT PASS/FAIL lines (verdict checks), MODEL lines (not verdict rows), INFO lines."""
import csv, sys, re, os, statistics, math
raw = sys.argv[1]
arms = {}
for line in open(os.path.join(raw, 'arms.txt')):
    m = re.match(r'ARM (\S+) (.*)', line)
    arms[m.group(1)] = dict(x.split('=', 1) for x in m.group(2).split() if '=' in x)
def rd(p): return list(csv.DictReader(open(p)))
res = []
def check(name, ok, detail): res.append(ok); print(('RESULT PASS ' if ok else 'RESULT FAIL ') + name + ' :: ' + detail)
CH = 16 * 1024
def ratio_count(T, S):
    for k in range(1, 21):
        if T / 2 ** k < S: return k
    return 20
def maxpart_of(ops, ret):
    # partition size = growth of the operand between consecutive calls inside one piece; after a switch the next operand is the first partition of the new piece
    d = []
    for i in range(len(ops) - 1):
        d.append(ops[i + 1] if ret[i] == 1 else ops[i + 1] - ops[i])
    return d
summary = {}
for tag in sorted(arms):
    kv = arms[tag]; kind = kv['kind']; P = int(kv['param']); inb = int(kv['inputBytes'])
    comp = kv.get('compressed') == 'true'
    calls = rd(f'{raw}/calls-{tag}.csv'); files = rd(f'{raw}/files-{tag}.csv')
    n = len(files); sizes = [int(f['data_file_bytes']) for f in files]
    ops = [int(c['operand']) for c in calls]; ret = [int(c['returned']) for c in calls]
    d = maxpart_of(ops, ret); mp = max(d) if d else 0
    gran = (2 * CH + 64) if comp else 0
    summary[tag] = dict(n=n, out=sum(sizes), inb=inb, kind=kind, P=P)
    print(f'ARM {tag}: kind={kind} param={P} input={inb} outputs={n} outputBytes={sum(sizes)} switches={sum(ret)} calls={len(calls)} maxPartition={mp}')
    check(f'{tag}: rows preserved, outputs == switches + 1', int(kv['outputRows']) == int(kv['partitionsAppended']) * 10 and n == sum(ret) + 1, f"outputRows={kv['outputRows']} partitions={kv['partitionsAppended']} outputs={n} switches={sum(ret)}")
    check(f'{tag}: output bytes within 2% of input bytes', abs(sum(sizes) - inb) <= 0.02 * inb, f'out={sum(sizes)} in={inb} diff={(sum(sizes)-inb)/inb*100:.3f}%')
    if kind == 'max':
        check(f'{tag}: operand at every true return > m, every false return <= m', all((o > P) == (r == 1) for o, r in zip(ops, ret)), f'min true={min([o for o,r in zip(ops,ret) if r==1], default=None)} max false={max([o for o,r in zip(ops,ret) if r==0], default=None)}')
        nonfinal = sizes[:-1]
        check(f'{tag}: every non-final output in (m, m + maxPartition]', all(P < s <= P + mp for s in nonfinal), f'min={min(nonfinal, default=None)} max={max(nonfinal, default=None)} m={P} maxPart={mp}')
        exp = inb / P
        check(f'{tag}: output count within 1 of T/m', abs(n - exp) <= 1.0 + 1e-9 or abs(n - round(exp)) <= 1, f'outputs={n} T/m={exp:.2f}')
        continue
    T = int(kv['totalSize']); rl = int(kv['ratiosLength']); exp_rl = ratio_count(T, P)
    ops_t = [int(c['target_before']) for c in calls]; idx_b = [int(c['ratio_idx_before']) for c in calls]; idx_a = [int(c['ratio_idx_after']) for c in calls]
    check(f'{tag}: T == input Data.db length', T == inb, f'T={T} input={inb}')
    check(f'{tag}: ratios.length == first k with T/2^k < smallest (max 20) (B2i.2)', rl == exp_rl, f'ratios.length={rl} expected={exp_rl}')
    # line 84: true iff operand > currentBytesToWrite and index < len-1
    check(f'{tag}: line-84 rule holds on every call (true iff operand > currentBytesToWrite and idx < len-1)', all((r == 1) == (o > t and ib < rl - 1) for o, r, t, ib in zip(ops, ret, ops_t, idx_b)), f'calls={len(calls)}')
    targets = [math.floor(T * 2 ** -(i + 1) + 0.5) for i in range(rl)]  # Math.round semantics (half up), not Python's banker's rounding
    check(f'{tag}: target at switch i is round(T * 2^-(i+1))', all(ops_t[c] == targets[idx_b[c]] for c in range(len(calls))), 'currentBytesToWrite at every call equals round(T*ratio[idx])')
    nonfinal = sizes[:-1]
    ok = all(targets[i] < s <= targets[i] + mp + gran for i, s in enumerate(nonfinal))
    check(f'{tag}: every non-final output i in (target_i, target_i + maxPartition + granularity]', ok, f'maxPart={mp} gran={gran} excess_max={max([s - targets[i] for i, s in enumerate(nonfinal)], default=None)}')
    if not comp:
        sw = [o for o, r in zip(ops, ret) if r == 1]
        check(f'{tag}: instrument: non-final Data.db length == operand at its switch (uncompressed)', sw == nonfinal, f'first mismatch: {[(a,b) for a,b in zip(sw,nonfinal) if a!=b][:2]}')
    # B2f numbers
    if tag in ('d50', 'd50z'):
        check(f'{tag}: gate 200e6 <= T < 400e6', 200e6 <= T < 400e6, f'T={T}')
        check(f'{tag}: ratios.length == 3, N == 3, switch count == 2', rl == 3 and n == 3 and sum(ret) == 2, f'ratios.length={rl} N={n} switches={sum(ret)}')
        check(f'{tag}: last output (remainder) > its own target T*ratios[last] (no hard stop on the last piece)', sizes[-1] > targets[-1], f'last={sizes[-1]} target={targets[-1]} smallest={P} (last>smallest: {sizes[-1] > P})')
    if tag == 'd5':
        check('d5: gate 160e6 <= T < 320e6; ratios.length == 6, N == 6', 160e6 <= T < 320e6 and rl == 6 and n == 6, f'T={T} ratios.length={rl} N={n}')
        check('d5: last output > its own target', sizes[-1] > targets[-1], f'last={sizes[-1]} target={targets[-1]}')
    if tag == 'dbig':
        check('dbig: ratios.length == 1, N == 1, no switch, output ~ T', rl == 1 and n == 1 and sum(ret) == 0 and abs(sizes[0] - T) <= 0.02 * T, f'ratios.length={rl} N={n} size={sizes[0]}')
    if tag == 'small':
        check('small: gate T < 100e6; ratios.length == 1, N == 1, output below the 50e6 constant', T < 100e6 and rl == 1 and n == 1 and sizes[0] < P, f'T={T} ratios.length={rl} N={n} size={sizes[0]} constant={P}')
    if tag == 'd0':
        check('d0: ratios.length == 20, 2 <= N <= 20, switches == N-1', rl == 20 and 2 <= n <= 20, f'ratios.length={rl} N={n}')
        check('d0: last output holds the remainder and exceeds its own target T*ratios[19]', sizes[-1] > targets[-1], f'last={sizes[-1]} target={targets[-1]}')
        # model: pieces take floor(target/p)+1 partitions of the median size p until partitions run out; last piece takes the rest
        p = statistics.median(d); nparts = int(kv['partitionsAppended']); left = nparts; npieces = 0
        for i in range(rl):
            npieces += 1
            if i == rl - 1: left = 0; break
            take = int(targets[i] // p) + 1; left -= take
            if left <= 0: break
        print(f'{"MODEL PASS" if npieces == n else "MODEL FAIL"} d0: model N={npieces} observed N={n} (median partition {p}; not a verdict row)')
# cross-arm
sp = {t: v for t, v in summary.items() if v['kind'] == 'split' and t in ('d0', 'd5', 'd50', 'dbig')}
if len(sp) == 4:
    outs = [v['out'] for v in sp.values()]
    check('cross: output bytes the same (within 2%) for smallest = 0, 5e6, 50e6, 10*T while N changes', max(outs) - min(outs) <= 0.02 * min(outs) and len({v['n'] for v in sp.values()}) == 4, 'out=' + str({t: v["out"] for t, v in sp.items()}) + ' N=' + str({t: v["n"] for t, v in sp.items()}))
    check('cross: N falls as the constant rises (d0 > d5 > d50 > dbig == 1)', sp['d0']['n'] > sp['d5']['n'] > sp['d50']['n'] > sp['dbig']['n'] == 1, str({t: v["n"] for t, v in sp.items()}))
if 'ctl20' in summary and 'ctl40' in summary:
    check('control: MaxSSTableSizeWriter count falls when m rises (positive control moves with its knob)', summary['ctl20']['n'] > summary['ctl40']['n'] >= 2, f"m=20e6 N={summary['ctl20']['n']}, m=40e6 N={summary['ctl40']['n']}")
print('SUMMARY', 'ALL PASS' if all(res) else f'{res.count(False)} FAIL of {len(res)}', f'({len(res)} checks)')
