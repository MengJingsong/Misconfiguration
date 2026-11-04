#!/usr/bin/env python3
"""Independent re-parse of the raw files of the run (cluster: <label>/raw/*; unit: unit/setter.out, unit/harness.out) against the case file's
predictions. Does not use the run script's own EXPECTED lines. usage on the node: selfcheck.py [~/s4b-logs/rss2]"""
import glob, math, os, re, sys
R = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/s4b-logs/rss2')
bad = 0
def chk(name, ok, detail=''):
    global bad
    bad += (not ok)
    print(('PASS ' if ok else 'FAIL ') + name + (' | ' + detail if detail else ''))
# depth table from the unit tier's harness.out (Murmur3)
dt = None
for l in open(R + '/unit/harness.out'):
    m = re.match(r'STAGE4 value U3 depth_table Murmur3Partitioner leaf=(\d+) inner=(\d+) .*', l)
    if m: dt = (int(m.group(1)), int(m.group(2)))
leaf, inner = dt
def d(b): return max(1, int(math.floor(math.log(max(1, (b + inner) // (leaf + inner))) / math.log(2))))
def i32(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x >= (1 << 31) else x
def Lpred(s, n, RF=2):
    avail = int(i32(s * 1048576) / RF)
    return 2 ** int(min(math.ceil(math.log(n) / math.log(2)), min(d(max(1, avail)), 20)))
def reads(tag_glob):
    out = {}
    for f in sorted(glob.glob(tag_glob)):
        t = open(f, errors='replace').read()
        out[f] = (re.findall(r'Created (\d+) merkle trees with merkle trees size (\d+), (\d+) partitions', t), [int(x) for x in re.findall(r'Prepared AEService trees of size (\d+) for', t)],
                  [int(x) for x in re.findall(r'Allocating direct buffer of size (\d+) for an off-heap merkle tree', t)])
    return out
# every repair of m-control, m-a, m-range: L from the debug logs vs the formula, and the off-heap buffers
steps = {}
for lab in ('m-control', 'm-a', 'm-range'):
    for f in glob.glob(f'{R}/{lab}/raw/*-N1-debug.log'):
        base = os.path.basename(f)[:-len('-N1-debug.log')]
        steps[(lab, base)] = f
SVAL = {}
for (lab, base), f in sorted(steps.items()):
    m = re.search(r'-s(\d+)$', base)
    s = int(m.group(1)) if m else 128 if 'sdefault' in base else None
    if s is None: continue
    for node in ('N1', 'N2'):
        t = open(f.replace('-N1-', f'-{node}-'), errors='replace').read()
        cre = re.findall(r'Created (\d+) merkle trees with merkle trees size (\d+), (\d+) partitions', t)
        pre = [int(x) for x in re.findall(r'Prepared AEService trees of size (\d+) for', t)]
        n = int(cre[0][2]) if cre else None
        exp = Lpred(s, n) if n else None
        chk(f'{lab} {base} {node}: L (log) == formula', len(pre) == 1 and pre[0] == exp, f'L={pre} formula={exp} n={n}')
        if node == 'N1':
            off = sorted(int(x) for x in re.findall(r'Allocating direct buffer of size (\d+) for an off-heap merkle tree', t))
            chk(f'{lab} {base} N1: off-heap buffers == 2 x (82 L + 32)', off == [82 * pre[0] + 32] * 2, f'{off}')
        SVAL[(lab, base, node)] = pre[0] if pre else None
# heap histograms: delta between idle and hold == L (leaf), L-1 (inner)
for lab in ('m-control', 'm-a', 'm-range'):
    for fi in glob.glob(f'{R}/{lab}/raw/*-N2-histo-idle.txt'):
        fh = fi.replace('idle', 'hold')
        def cnt(f, cls):
            m = re.search(r'\d+:\s+(\d+)\s+\d+\s+org\.apache\.cassandra\.utils\.MerkleTree\$' + cls + r'\s', open(f).read())
            return int(m.group(1)) if m else 0
        base = os.path.basename(fi)[:-len('-N2-histo-idle.txt')]
        L = SVAL.get((lab, base, 'N2'))
        dl = cnt(fh, 'OnHeapLeaf') - cnt(fi, 'OnHeapLeaf'); di = cnt(fh, 'OnHeapInner') - cnt(fi, 'OnHeapInner')
        chk(f'{lab} {base} N2 heap: OnHeapLeaf +L, OnHeapInner +(L-1)', L is not None and dl == L and di == L - 1, f'+{dl} +{di} L={L}')
# range arm: the rejected writes
s = open(f'{R}/m-range/summary.txt').read()
for bad_v in ('0', '-5'):
    chk(f'range: write {bad_v} rejected on both nodes with the setter text, read-back 4',
        len(re.findall(rf'REJECT N[12] set {bad_v}: failed=True read back 4 \| SETFAIL .*Cannot set repair_session_space to {bad_v} < 1 mebibyte', s)) == 2)
chk('range: write 2147483647 rejected on both nodes (type bound), read-back 4',
    len(re.findall(r'REJECT N[12] set 2147483647: failed=True read back 4 \| SETFAIL .*Invalid data storage: 2147483647 mebibytes', s)) == 2)
chk('range: write 2147483646 accepted on both nodes', len(re.findall(r'ACCEPT N[12] set 2147483646: failed=False read back 2147483646', s)) == 2)
# the rejected value left the next tree where it was
def Lof(lab, base): return SVAL.get((lab, base, 'N1'))
a = Lof('m-range', 'R-accepted-s4'); b0 = Lof('m-range', 'R-after-rejected-0-s4'); b5 = Lof('m-range', 'R-after-rejected-5-s4')
chk('range: L after rejected 0 and -5 equals L before (8192)', a == b0 == b5 == 8192, f'{a} {b0} {b5}')
chk('range: L at 2147483646 is 2 (overflow)', Lof('m-range', 'R-int-max-minus-1-s2147483646') == 2)
# control: sweep doubles per doubling
sw = {int(re.search(r's(\d+)$', b).group(1)): Lof('m-a', b) for (lab, b, nd) in SVAL if lab == 'm-a' and nd == 'N1' and re.fullmatch(r'A-s\d+', b)}
chk('control: L at 1,4,16,64 MiB == 2048, 8192, 32768, 131072', [sw.get(k) for k in (1, 4, 16, 64)] == [2048, 8192, 32768, 131072], str(sw))
# unit tier
so = open(R + '/unit/setter.out').read()
mm = re.findall(r'^STAGE4 check (.*) (?:expected=.*)? MISMATCH', so, re.M)
print('unit setter MISMATCH lines:'); [print('   ', m) for m in re.findall(r'^STAGE4 check .* MISMATCH$', so, re.M)]
chk('unit setter: exactly the 5 recorded mismatches (MAX_VALUE x3, raw -1/-1000 not constructible)', len(re.findall(r'MISMATCH$', so, re.M)) == 5)
ho = open(R + '/unit/harness.out').read()
chk('closed RepairSessionSpaceTreeTest: 78 checks ok, 0 MISMATCH', len(re.findall(r'^STAGE4 check .* ok$', ho, re.M)) == 78 and 'MISMATCH' not in ho)
print('FAILS', bad)
sys.exit(1 if bad else 0)
