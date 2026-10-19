#!/usr/bin/env python3
"""Independent self-check of run 1, repair_session_space-split-maxsize (results section 5).

Re-parses the raw files, not the run script's summaries: the unit tier's STAGE4 lines and JUnit XML, and for the
cluster tier each repair's debug.log and trace segments, the jmap histograms and the direct-memory readings kept under
~/stage4-logs/rss/<label>/raw/, plus the knob read-backs in session.log. Recomputes every prediction from the case's 9a
formula, L = 2^min(ceil(log2 n), d(b), D), taking d(b) from the depth table the unit tier printed (no code is shared
with cluster-run.py). Prints one line per check and exits 1 if any load-bearing check fails.
usage: selfcheck.py [logs-root]          (default ~/stage4-logs/rss)
"""
import glob, math, os, re, sys, xml.etree.ElementTree as ET

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/rss')
fails = []
n_checks = 0


def check(name, ok, detail=''):
    global n_checks
    n_checks += 1
    print(f'{"PASS" if ok else "FAIL"} {name}' + (f' — {detail}' if detail else ''))
    if not ok:
        fails.append(name)
    return ok


def read(path):
    with open(path, errors='replace') as f:
        return f.read()


# ---------------------------------------------------------------- unit tier

U = read(f'{ROOT}/unit/harness.out')
for cls in ('org.apache.cassandra.utils.MerkleTreeTest', 'org.apache.cassandra.repair.ValidatorTest',
            'org.apache.cassandra.repair.RepairSessionSpaceTreeTest'):
    x = ET.parse(f'{ROOT}/unit/TEST-{cls}.xml').getroot()
    check(f'unit {cls.split(".")[-1]} JUnit', x.get('failures') == '0' and x.get('errors') == '0' and int(x.get('tests')) > 0,
          f'tests={x.get("tests")} failures={x.get("failures")} errors={x.get("errors")}')
check('unit harness: no MISMATCH line', 'MISMATCH' not in U, f'{U.count("STAGE4 check")} checks')

# depth table per partitioner, as printed by U3
table = {}
for m in re.finditer(r'STAGE4 value U3 depth_table (\S+) leaf=(\d+) inner=(\d+) leaf\+inner=(\d+) (.*)', U):
    table[m.group(1)] = dict(leaf=int(m.group(2)), inner=int(m.group(3)),
                             d={int(k) * 1024: int(v) for k, v in re.findall(r'd\((\d+)KiB\)=(\d+)', m.group(5))})
for p, t in table.items():
    check(f'unit {p}: leaf+inner in (128, 256] (case 4, from ValidatorTest)', 128 < t['leaf'] + t['inner'] <= 256, f'{t["leaf"] + t["inner"]}')
    ds = [t['d'][b] for b in sorted(t['d'])]
    check(f'unit {p}: d rises by one per doubling of b (0.5 to 8 MiB)', ds[:5] == list(range(ds[0], ds[0] + 5)), str(t['d']))


def d_of(part, b):
    """d(b): from the printed table when b is in it, else MerkleTree.java:1538-1540 with the printed sizes."""
    t = table[part]
    if b in t['d']:
        return t['d'][b]
    adj = max(1, (b + t['inner']) // (t['leaf'] + t['inner']))
    return max(1, int(math.floor(math.log(adj) / math.log(2))))


def j_int(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x & (1 << 31) else x


def predict(part, s, rf, n, cap=20):
    b = max(1, int(int(j_int(s * 1048576) / rf)))      # ValidationManager.java:62-63, :71 (share 1)
    depth = min(math.ceil(math.log(n) / math.log(2)), min(d_of(part, b), cap))
    return 2 ** depth

# U3 / U4 readings against the 9e literal predictions and against the formula, recomputed here
lit = {('U3 init', 1): 4096, ('U3 init', 2): 8192, ('U3 init', 4): 16384, ('U3 split', 1): 4096, ('U3 split', 2): 8192,
       ('U3 depthcap10', 64): 1024, ('U4', 2047): 16384, ('U4', 2048): 2, ('U4', 4096): 2, ('U4', 4097): 4096, ('U4', 5120): 16384}
for m in re.finditer(r'STAGE4 value (U3 init|U3 split|U3 depthcap10|U4) s=(\d+) n=(\d+) ceil_log2_n=\d+ trees=(\d+) size=(\d+) maxsize=(\d+) leaves=(\d+)', U):
    kind, s, n, trees, size, maxsize, leaves = m.group(1), *map(int, m.groups()[1:])
    cap = 10 if kind == 'U3 depthcap10' else 20
    f = predict('ByteOrderedPartitioner', s, 1, n, cap)
    check(f'unit {kind} s={s}: leaves = 9e prediction {lit[(kind, s)]} and formula {f}', leaves == lit[(kind, s)] == f and trees == 1 and size == leaves,
          f'n={n} leaves={leaves} size={size} maxsize={maxsize}')
    if kind == 'U3 split':
        check(f'unit {kind} s={s}: split loop stopped at size == maxsize (capacity, not TooDeep)', size == maxsize)
for s, prod in ((2048, -2147483648), (4096, 0), (4097, 1048576), (5120, 1073741824)):
    m = re.search(rf'STAGE4 value U4 s={s} int_product=(-?\d+)', U)
    check(f'unit U4 s={s}: 32-bit product {prod}', m and int(m.group(1)) == prod == j_int(s * 1048576), m.group(1) if m else 'missing')
# U1, U2
for M in (2, 1024, 16384):
    ok = all(re.search(rf'STAGE4 check U1 M={M} {c} .* ok', U) for c in
             ('first_false_reached', 'size_at_first_false', 'leaves_counted', 'successful_splits', 'further_calls_all_false',
              'size_unchanged_after_1000_refusals', 'refused_alloc_within_baseline', 'success_alloc_at_least_inner_plus_2_leaves'))
    ra = re.search(rf'STAGE4 value U1 M={M} refused_alloc max_bytes=(\d+) baseline=(\d+)', U)
    check(f'unit U1 M={M}: refuses at size == M, creates nothing after; refused calls allocate <= baseline', ok and ra and int(ra.group(1)) <= int(ra.group(2)),
          f'refused max {ra.group(1)} B, baseline {ra.group(2)} B' if ra else '')
for M, exp in ((2, 2), (1024, 1024), (16384, 16384), (1000, 512)):
    check(f'unit U2 M={M}: init() builds {exp} leaves', bool(re.search(rf'STAGE4 check U2 M={M} leaves_counted expected={exp} actual={exp} ok', U)))

# ---------------------------------------------------------------- cluster tier

def parse_repair(raw, tag):
    out = {}
    for node in ('N1', 'N2'):
        dl = read(f'{raw}/{tag}-{node}-debug.log')
        tr = read(f'{raw}/{tag}-{node}-trace.log')
        created = re.findall(r'Created (\d+) merkle trees with merkle trees size (\d+), (\d+) partitions', dl)
        prepared = re.findall(r'Prepared AEService trees of size (\d+) for', dl)
        out[node] = dict(
            created=created, prepared=[int(x) for x in prepared],
            n=int(created[0][2]) if len(created) == 1 else None,
            L=int(prepared[0]) if len(prepared) == 1 else None,
            off=sorted(int(x) for x in re.findall(r'Allocating direct buffer of size (\d+)', dl)),
            calls=[int(x) for x in re.findall(r'split calls=(\d+)', tr)],
            refused=[tuple(map(int, x)) for x in re.findall(r'split refused size=(\d+) maxsize=(\d+)', tr)],
            toodeep=[tuple(map(int, x)) for x in re.findall(r'split toodeep size=(\d+) maxsize=(\d+)', tr)],
            samples=[int(x) for x in re.findall(r'samples=(\d+)', tr)],
            hold=tr.count('hold start'))
    return out


def histo_counts(path):
    txt = read(path)
    c = {}
    for m in re.finditer(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+org\.apache\.cassandra\.utils\.MerkleTree\$(OnHeapLeaf|OnHeapInner)\b', txt, re.M):
        c[m.group(3)] = (int(m.group(1)), int(m.group(2)))
    return c.get('OnHeapLeaf', (0, 0)), c.get('OnHeapInner', (0, 0))


def knob_readbacks(label):
    return [(node, int(a), int(b), int(c)) for node, a, b, c in
            re.findall(r'KNOB (N\d) set (\d+) read back (-?\d+) / (-?\d+)', read(f'{ROOT}/{label}/summary.txt'))]


L_by_s = {}
plans = [('m-control', 'M', [('control', 'default'), ('control-hold', 'default')]),
         ('m-a', 'M', [(st, s) for s in (1, 4, 16, 64) for st in ('A', 'A-hold')]),
         ('m-b', 'M', [('B', 4), ('B', 16)]),
         ('m-c', 'M', [('C-overflow', 2048), ('C-overflow', 4097)]),
         ('m-depth', 'M', [('C-depthcap15', 64)]),
         ('o-run', 'O', [('A', 4), ('A', 16)])]
part_of = {'M': 'Murmur3Partitioner', 'O': 'ByteOrderedPartitioner'}
DEFAULT_S = None
m = re.search(r"DEFAULT repair_session_space read back \{'N1': (\d+), 'N2': (\d+)\}", read(f'{ROOT}/m-setup/summary.txt'))
check('cluster: default repair_session_space read back 128 on both nodes', m and m.group(1) == m.group(2) == '128', m.group(0) if m else 'missing')
DEFAULT_S = int(m.group(1)) if m else 128

for label, arm, runs in plans:
    raw = f'{ROOT}/{label}/raw'
    for node, s, b1, b2 in knob_readbacks(label):
        check(f'{label}: knob {node} set {s} read back {b1}/{b2}', s == b1 == b2)
    for step, s in runs:
        tag = re.sub(r'[^A-Za-z0-9]+', '-', f'{step}-s{s}').strip('-')
        sv = DEFAULT_S if s == 'default' else s
        cap = 15 if step == 'C-depthcap15' else 20
        r = parse_repair(raw, tag)
        for node in ('N1', 'N2'):
            x = r[node]
            check(f'{label} {step} s={s} {node}: one Created and one Prepared line', x['n'] is not None and x['L'] is not None,
                  f'{len(x["created"])}/{len(x["prepared"])}')
            if x['n'] is None or x['L'] is None:
                continue
            pred = predict(part_of[arm], sv, 2, x['n'], cap)
            check(f'{label} {step} s={s} {node}: L = 2^min(ceil log2 n, d(b), D) = {pred}', x['L'] == pred, f'n={x["n"]} L={x["L"]}')
            check(f'{label} {step} s={s} {node}: partition term not binding (ceil log2 n > log2 L)', math.ceil(math.log2(x['n'])) > math.log2(x['L']),
                  f'ceil log2 n = {math.ceil(math.log2(x["n"]))}')
            check(f'{label} {step} s={s} {node}: one split-calls line', len(x['calls']) == 1, str(x['calls']))
            if arm == 'M':
                check(f'{label} {step} s={s} {node}: split() never called, no refusal line', x['calls'] == [0] and not x['refused'] and not x['toodeep'])
            else:
                check(f'{label} {step} s={s} {node}: one capacity refusal at size == maxsize == L, no TooDeep',
                      x['refused'] == [(x['L'], x['L'])] and not x['toodeep'], f'refused={x["refused"]} toodeep={x["toodeep"]}')
                check(f'{label} {step} s={s} {node}: split calls = L (L - 1 splits + 1 refused)', x['calls'] == [x['L']], str(x['calls']))
                check(f'{label} {step} s={s} {node}: samples ~ n/128 (within 2 %)', len(x['samples']) == 1 and abs(x['samples'][0] - x['n'] / 128) <= 0.02 * x['n'] / 128,
                      f'samples={x["samples"]} n/128={x["n"] / 128:.0f}')
            L_by_s.setdefault((arm, step.replace('-hold', ''), s), {})[node] = x['L']
        # off heap, coordinator
        if arm == 'M':
            want = sorted(82 * r[n]['L'] + 32 for n in ('N1', 'N2'))
            check(f'{label} {step} s={s} N1: two off-heap buffers of 82 L + 32 = {want}', r['N1']['off'] == want and not r['N2']['off'], f'N1 {r["N1"]["off"]} N2 {r["N2"]["off"]}')
        else:
            check(f'{label} {step} s={s}: no off-heap buffer line on either node', not r['N1']['off'] and not r['N2']['off'])
        if step.endswith('-hold'):
            check(f'{label} {step} s={s} N2: hold started once', r['N2']['hold'] == 1)
            (l0, b0), (i0, c0) = histo_counts(f'{raw}/{tag}-N2-histo-idle.txt')
            (l1, b1), (i1, c1) = histo_counts(f'{raw}/{tag}-N2-histo-hold.txt')
            L2 = r['N2']['L']
            check(f'{label} {step} s={s} N2 heap: OnHeapLeaf +{L2}, OnHeapInner +{L2 - 1}', (l1 - l0, i1 - i0) == (L2, L2 - 1),
                  f'+{l1 - l0} ({b1 - b0} B), +{i1 - i0} ({c1 - c0} B); {((b1 - b0) + (c1 - c0)) / L2:.1f} B per leaf shallow')
            di = int(re.search(r'MemoryUsed (\d+)', read(f'{raw}/{tag}-N1-direct-idle.txt')).group(1))
            dh = int(re.search(r'MemoryUsed (\d+)', read(f'{raw}/{tag}-N1-direct-hold.txt')).group(1))
            one = 82 * r['N1']['L'] + 32
            print(f'INFO {label} {step} s={s} N1 direct MemoryUsed rise during hold {dh - di} B against one buffer {one} B '
                  f'({(dh - di) / one:.4f}) — support only')

# ---------------------------------------------------------------- the 9a logic across values

def L(arm, step, s):
    v = L_by_s.get((arm, step, s), {})
    return v.get('N1') if v.get('N1') == v.get('N2') else None

seq = [L('M', 'A', s) for s in (1, 4, 16, 64)] + [L('M', 'control', 'default')]
check('logic (3): arm M, L quadruples per quadrupling of s (1, 4, 16, 64 MiB) and doubles to the default (128)',
      None not in seq and all(seq[i + 1] == 4 * seq[i] for i in range(3)) and seq[4] == 2 * seq[3], str(seq))
check('logic, scenario B: doubling the data leaves L unchanged at s = 4 and 16',
      L('M', 'B', 4) == L('M', 'A', 4) and L('M', 'B', 16) == L('M', 'A', 16), f'{L("M", "B", 4)}, {L("M", "B", 16)}')
check('logic (6): s = 2048 gives 2 leaves; s = 4097 gives the s = 1 count', L('M', 'C-overflow', 2048) == 2 and L('M', 'C-overflow', 4097) == L('M', 'A', 1),
      f'{L("M", "C-overflow", 2048)}, {L("M", "C-overflow", 4097)} vs {L("M", "A", 1)}')
check('depth cap 15 at s = 64: L = 2^15', L('M', 'C-depthcap15', 64) == 1 << 15, str(L('M', 'C-depthcap15', 64)))
check('logic (4): arm O, same L as arm M at 4 and 16', L('O', 'A', 4) == L('M', 'A', 4) and L('O', 'A', 16) == L('M', 'A', 16),
      f'{L("O", "A", 4)}, {L("O", "A", 16)}')
dep = read(f'{ROOT}/m-depth/summary.txt')
check('depth cap step: the deprecation warning logged on both nodes', 'DEPTH deprecation warnings: 2' in dep)

print(f'\n{n_checks} checks, {len(fails)} failed' + (': ' + '; '.join(fails) if fails else ''))
sys.exit(1 if fails else 0)
