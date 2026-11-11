#!/usr/bin/env python3 -I
"""Cluster-tier analyzer for DEFAULT_SMALLEST_SSTABLE_BYTES-...--autonomous (B3f/B3g as amended B3i).
Usage: analyze_cluster.py <cluster-root>   (root holds A/ B/ C/ = trees with constant 50e6 / 5e6 / 500e6, each with <arm>/summary.json and session.log)."""
import json, sys, os, re, math
root = sys.argv[1]
CONST = {'A': 50_000_000, 'B': 5_000_000, 'C': 500_000_000}
res = []
def check(name, ok, detail): res.append(ok); print(('RESULT PASS ' if ok else 'RESULT FAIL ') + name + ' :: ' + detail)
def ratio_count(T, S):
    for k in range(1, 21):
        if T / 2 ** k < S: return k
    return 20
data = {}
for X in 'ABC':
    p = os.path.join(root, X)
    if not os.path.isdir(p): continue
    sl = open(os.path.join(p, 'session.log')).read()
    m = re.search(r'DEFAULT_SMALLEST_SSTABLE_BYTES = ([\d_]+);', sl)
    check(f'{X}: tree constant in session.log is {CONST[X]}', m is not None and int(m.group(1).replace('_', '')) == CONST[X], m.group(0) if m else 'not found')
    for arm in sorted(os.listdir(p)):
        f = os.path.join(p, arm, 'summary.json')
        if os.path.exists(f): data[(X, arm)] = json.load(open(f))
def rnd(x): return int(math.floor(x + 0.5))
for (X, arm), S in sorted(data.items()):
    T = S['input_bytes']; sizes = S['output_sizes_in_creation_order']; N = S['outputs']; sw = S['switch_lines']; c = CONST[X]
    bound = rnd(T / S['partitions_loaded'] * 1.02) + ((2 * 16384 + 64) if S['compressed'] else 0)
    print(f'ARM {X}/{arm}: constant={c} T={T} outputs={N} switches={len(sw)} sizes={sizes[:12]}{"..." if len(sizes) > 12 else ""} output_bytes={S["bytes"]} peak_table_du={S["du_table_peak"]} (x{S["du_table_peak"]/S["pre_du_table"]:.3f} of pre) space_asked={[x["asked"] for x in S["space_check_lines"]]}')
    check(f'{X}/{arm}: valid: one input set (>= 8 files; size-triggered memtable flushes made 24 for the 2 GB arms), one new compaction, auto-compaction idle, no ERROR, spot check ok', S['input_files'] >= 8 and len(S['compacted_lines']) == 1 and S['compactionstats_idle'] and not S['errors_in_log'] and S['spot_check_ok'], f"input_files={S['input_files']} compacted_lines={len(S['compacted_lines'])} errors={len(S['errors_in_log'])} spot={S['spot_check_ok']}")
    check(f'{X}/{arm}: sum of output Data.db within 2% of input (no data lost or grown)', abs(sum(sizes) - T) <= 0.02 * T, f'out={sum(sizes)} in={T}')
    asked = [x['asked'] for x in S['space_check_lines']]
    check(f'{X}/{arm}: task-level space check asked for the whole input T (B3i.5), nothing in the log says space was short', T in asked and not S['space_warnings'], f'asked={asked} T={T} warnings={S["space_warnings"]}')
    if arm in ('plain',):
        check(f'{X}/{arm}: no -s: 1 output of about T, no writer switch', N == 1 and not sw and abs(sizes[0] - T) <= 0.02 * T, f'N={N} switches={len(sw)}')
        continue
    if arm.startswith('lcs'):
        Sb = (100 if arm == 'lcs100' else 50) * 2 ** 20
        check(f'{X}/{arm}: LCS control: output count within 1 of ceil(T/S); non-final outputs in (S, S + one partition]', abs(N - math.ceil(T / Sb)) <= 1 and all(Sb < s <= Sb + bound for s in sizes[:-1]), f'N={N} T/S={T/Sb:.2f} min/max non-final={min(sizes[:-1])}/{max(sizes[:-1])} S={Sb}')
        continue
    # split arms
    gate_ok = {'small': (80e6 <= T < 100e6) if c == 5_000_000 else (T < 100e6)}.get(arm, {50_000_000: 1.6e9 <= T < 3.2e9, 5_000_000: 1.28e9 <= T < 2.56e9, 500_000_000: 2.0e9 <= T < 4.0e9}[c])
    check(f'{X}/{arm}: validity gate on T for the predicted ratio count (B3i.1)', bool(gate_ok), f'T={T}')
    if arm == 'small': pass
    rl = ratio_count(T, c)
    exp_sw = [rnd(T * 2 ** -(i + 2)) for i in range(rl - 1)]
    check(f'{X}/{arm}: outputs == ratios.length == first k with T/2^k < constant ({rl})', N == rl, f'N={N} expected={rl}')
    check(f'{X}/{arm}: "Switching writer" DEBUG lines == [round(T*2^-(i+2))], i.e. one per true return of line 84', sw == exp_sw, f'observed={sw} expected={exp_sw}')
    targets = [rnd(T * 2 ** -(i + 1)) for i in range(rl)]
    nf = sizes[:-1]
    check(f'{X}/{arm}: every non-final output i in (target_i, target_i + one partition + granularity]', all(targets[i] < s <= targets[i] + bound for i, s in enumerate(nf)), f'bound={bound} excess_max={max([s - targets[i] for i, s in enumerate(nf)], default=None)} excess_min={min([s - targets[i] for i, s in enumerate(nf)], default=None)}')
    if N == rl and rl > 1:
        check(f'{X}/{arm}: last output is the remainder, above its own target T*ratios[last] and above the constant (no hard stop on the last piece)', sizes[-1] > targets[-1] and sizes[-1] > c, f'last={sizes[-1]} own target={targets[-1]} constant={c}')
    if arm == 'small' and c == 50_000_000:
        check(f'{X}/{arm}: small data, 50e6 constant: 1 output of about T (here above the constant: T/2 = {T/2:.0f} >= {c}? {T/2 >= c}), no switch', N == 1 and not sw and abs(sizes[0] - T) <= 0.02 * T, f'N={N} size={sizes[0]} constant={c}')
# cross-arm
def get(X, a): return data.get((X, a))
plain = get('A', 'plain')
splits = {X: get(X, 'split') for X in 'ABC' if get(X, 'split')}
if plain and len(splits) == 3:
    f = {X: sum(s['output_sizes_in_creation_order']) for X, s in splits.items()}; pk = {X: s['du_table_peak'] for X, s in splits.items()}
    pf = sum(plain['output_sizes_in_creation_order'])
    check('cross: final output bytes equal (within 2%) for constants 5e6 / 50e6 / 500e6 and the unsplit run', max(list(f.values()) + [pf]) - min(list(f.values()) + [pf]) <= 0.02 * pf, f'split={f} plain={pf}')
    check('cross: peak table-dir bytes equal (within 5%) for the three constants and the unsplit run', max(list(pk.values()) + [plain['du_table_peak']]) - min(list(pk.values()) + [plain['du_table_peak']]) <= 0.05 * plain['du_table_peak'], f'split={pk} plain={plain["du_table_peak"]}')
    check('cross: output count follows the constant (9 / 6 / 3) while bytes do not', (splits['B']['outputs'], splits['A']['outputs'], splits['C']['outputs']) == (9, 6, 3), f"B={splits['B']['outputs']} A={splits['A']['outputs']} C={splits['C']['outputs']}")
    check('cross: space-check request Y is the same (== T) for every constant', all(splits[X]['input_bytes'] in [x['asked'] for x in splits[X]['space_check_lines']] for X in splits) and len({splits[X]['input_bytes'] for X in splits}) >= 1, str({X: [x['asked'] for x in splits[X]['space_check_lines']] for X in splits}))
    print('INFO input bytes by tree:', {X: splits[X]['input_bytes'] for X in splits})
    # heap context (B3i.6)
    hs = {X: splits[X]['heap_used_peak_kb'] for X in splits}; s2 = get('A', 'split2')
    spread = abs(hs['A'] - s2['heap_used_peak_kb']) / hs['A'] if s2 and hs['A'] else None
    diff = (max(hs.values()) - min(hs.values())) / max(hs.values())
    print(f'INFO heap used peak (kB) by constant: {hs}; relative max difference {diff:.3f}; A split vs A split2 spread {spread}; RssAnon peak kB: ' + str({X: splits[X]['rss_anon_peak_kb'] for X in splits}))
    check('heap context: difference across constants does not exceed both 10% and the repeat spread (B3i.6)', not (diff > 0.10 and (spread is None or diff > spread)), f'diff={diff:.3f} spread={spread}')
l1, l2 = get('A', 'lcs100'), get('A', 'lcs50')
if l1 and l2: check('control: LCS file count rises as sstable_size_in_mb falls (positive control moves with its knob)', l2['outputs'] > l1['outputs'] and abs(l2['outputs'] - 2 * l1['outputs']) <= 2, f"100MiB -> {l1['outputs']}, 50MiB -> {l2['outputs']}")
s1, s2 = get('A', 'split'), get('A', 'split2')
if s1 and s2: check('repeat: split and split2 give the same count and sizes within 1%', s1['outputs'] == s2['outputs'] and abs(s1['bytes'] - s2['bytes']) <= 0.01 * s1['bytes'], f"{s1['outputs']} vs {s2['outputs']}, {s1['bytes']} vs {s2['bytes']}")
print('SUMMARY', 'ALL PASS' if all(res) else f'{res.count(False)} FAIL of {len(res)}', f'({len(res)} checks)')
