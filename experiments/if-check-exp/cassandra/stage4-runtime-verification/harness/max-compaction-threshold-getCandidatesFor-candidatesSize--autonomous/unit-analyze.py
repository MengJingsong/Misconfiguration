#!/usr/bin/env python3
"""unit-analyze.py <readings.txt>: judges B2f/B2g (with amendments U1-U5) of max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous.
Prints PASS/FAIL per prediction and the matched B2g row. Written before any unit reading."""
import sys, re, collections
R = {}
for l in open(sys.argv[1]):
    p = l.rstrip('\n').split(' ', 3)
    if p[0] == 'R' and len(p) == 4: R[(p[1], p[2])] = p[3]
def g(sec, key, cast=int):
    v = R.get((sec, key))
    if v is None: return None
    return {'true': True, 'false': False}.get(v, None) if cast is bool else cast(v)
fails, passes = [], []
def check(name, ok, note=''):
    (passes if ok else fails).append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ((' -- ' + note) if note else ''))

probes = collections.OrderedDict()      # tag -> dict
for (sec, key), v in R.items():
    if sec == 'step3':
        m = re.match(r'(.*)\.(knobN|sstableSizeMiB|candidateCount|candidateL0|candidateL1|candidateL0Bytes|candidateL1Bytes|candidateBytes|gateBytes|gateExceeded|outputLevel|candidate)$', key)
        if m: probes.setdefault(m.group(1), {})[m.group(2)] = {'true': True, 'false': False}.get(v, v)
fx = {}
for (sec, key), v in R.items():
    if sec == 'fixture':
        m = re.match(r'(.*)\.(l0sstables|l1sstables|l0bytes|l1bytes|overlapPairsL0L0|overlapPairsL0L1|overlapPairsL1L1)$', key)
        if m: fx.setdefault(m.group(1), {})[m.group(2)] = int(v)

def fixture_of(tag):
    if tag.startswith('small.schemaN'): return re.match(r'(small\.schemaN\d+\.rep\d)', tag).group(1)
    if tag.startswith('small.setter'): return 'small.setter'
    if tag.startswith('small20'): return 'small20'
    if tag.startswith('large'): return 'large.setter'
    if tag.startswith('groups'): return 'groups'
    return None

# instrument checks on the fixtures
for f, d in fx.items():
    n0 = d['l0sstables']
    ok = d['overlapPairsL0L0'] == (150 if f == 'groups' else n0 * (n0 - 1) // 2) and d['overlapPairsL1L1'] == 0 and \
         d['overlapPairsL0L1'] == (0 if f == 'groups' else n0 * d['l1sstables'])
    check(f'instrument: fixture {f} (L0 {n0}, L1 {d["l1sstables"]}) overlaps as designed', ok)

n_over = n_l1 = 0; rows = 0; l0_ok = True; gate_ok = True; bound_ok = True
byN = collections.defaultdict(list)
for tag, d in probes.items():
    if 'candidateCount' not in d: continue
    f = fx[fixture_of(tag)]; N = int(d['knobN']); n0f = f['l0sstables']; rows += 1
    exp_l0 = min(N, n0f)
    if int(d['candidateL0']) != exp_l0: l0_ok = False; print('  L0 count mismatch', tag, d['candidateL0'], 'expected', exp_l0)
    if int(d['candidateL0']) > N: bound_ok = False
    l1_in = int(d['candidateL1']) > 0
    gate = int(d['candidateL0Bytes']) > int(d['gateBytes'])
    expect_l1 = gate and f['l1sstables'] > 0
    if l1_in != expect_l1 or (l1_in and int(d['candidateL1']) != f['l1sstables']): gate_ok = False; print('  gate-rule mismatch', tag)
    if int(d['candidateCount']) > N: n_over += 1
    if l1_in: n_l1 += 1
    byN[(fixture_of(tag), d['sstableSizeMiB'])].append((N, d))
check('P1 L0 part of the candidate set = min(N, L0 sstables in the fixture) in every probe', l0_ok, f'{rows} probes')
check('P1b L0 count never exceeds N', bound_ok)
check('P2 L1 (all 10) is in the candidate set iff measured L0 candidate bytes > gate (strict)', gate_ok)
check('P2b total candidate count exceeds N in at least one probe (L1 added after the cap)', n_over > 0, f'{n_over} probes')
# specific large-class predictions
def get(tag, k): return probes.get(tag, {}).get(k)
for N, exp in ((4, False), (32, True), (64, True)):
    tag = f'large.setterN{N}.stcsL0On.gate160'
    v = get(tag, 'candidateL1')
    check(f'P2c large class N={N}: L1 {"included" if exp else "not included"}', v is not None and ((int(v) > 0) == exp), f'L0 bytes {get(tag, "candidateL0Bytes")}')
for N in (4, 8, 32, 64):
    ok = all(int(get(f'small.setterN{N}.stcsL0On.gate160', k) or -1) == v for k, v in (('candidateL1', 0),))
    check(f'P2d small class gate 160 N={N}: no L1', ok)
    tag = f'small.setterN{N}.gate1'; v = get(tag, 'candidateL1')
    check(f'P2e small class gate 1 MiB N={N}: L1 included (L0 bytes > 1 MiB)', v is not None and int(v) == 10)
# on/off identical
same = True
for tag in list(probes):
    if '.stcsL0On' in tag:
        o = tag.replace('.stcsL0On', '.stcsL0Off')
        if o in probes and any(probes[tag].get(k) != probes[o].get(k) for k in ('candidateCount', 'candidateL0', 'candidateL1', 'candidateBytes')): same = False; print('  on/off differ', tag)
check('P3 STCS-in-L0 on/off gives an identical candidate set (U3)', same)
# schema vs setter
ok = True
for N in (4, 8, 32, 64):
    s = get(f'small.schemaN{N}.rep1.gate160', 'candidateL0'); t = get(f'small.setterN{N}.stcsL0On.gate160', 'candidateL0')
    s2 = get(f'small.schemaN{N}.rep2.gate160', 'candidateL0')
    if not (s == t == s2 == str(N)): ok = False
check('P4 schema path (table option) and setter path give the same L0 count = N, 2 reps', ok)
# N=100 reference and 20-sstable variant
check('P5 N=100: no trim (L0 count 100)', get('small.setterN100.stcsL0On.gate160', 'candidateL0') == '100')
check('P5b 20 L0 sstables: L0 count = min(N, 20)', all(int(get(f'small20.setterN{n}.gate160', 'candidateL0') or -1) == min(n, 20) for n in (4, 8, 32)))
# groups
check('P6 group fixture: L0 count = min(N,100) (U4)', all(int(get(f'groups.setterN{n}.gate160', 'candidateL0') or -1) == min(n, 100) for n in (4, 8, 32, 64, 100)))
# STCS control
ctl = {}
for (sec, key), v in R.items():
    m = re.match(r'(.*)\.stcs\.N(\d+)\.(count|bytes|buckets)$', key)
    if sec == 'control' and m: ctl.setdefault((m.group(1), int(m.group(2))), {})[m.group(3)] = int(v)
okc = True; moved = True
for fam in ('small.setter', 'large.setter'):
    prev = -1
    for N in sorted({n for (f, n) in ctl if f == fam}):
        c = ctl[(fam, N)]
        if c['count'] != min(N, 100): okc = False; print('  stcs count', fam, N, c)
        if c['count'] <= prev: moved = False
        prev = c['count']
for N in (4, 8, 32, 64):
    c = ctl.get((f'small.schemaN{N}', N))
    if c and c['count'] != N: okc = False
check('P7 STCS control: bucket size = min(N, 100) for every N, rising with N (positive control moves)', okc and moved)
# truncate control
check('P8 instrument: truncate empties the table', R.get(('control', 'truncate.after')) == '0' and int(R.get(('control', 'truncate.before'), 0)) > 0)

print()
inst = [f for f in fails if f.startswith('instrument')]
if inst: row = 'INVALID (instrument)'
elif not bound_ok: row = 'B2g "L0 count > N": cap at :548 does not bind; claim confirmed, the trace is wrong'
elif not l0_ok: row = 'B2g "L0 count < N for all N / limit never reached" or other mismatch: Not confirmed'
elif n_over == 0 or n_l1 == 0: row = 'B2g "gate never crossed / no probe above N": Not confirmed' if fails else 'B2g Refuted'
elif fails and any(x.startswith('P7') for x in fails): row = 'B2g "STCS control does not scale with N": Not confirmed'
elif fails: row = 'Not confirmed (a prediction failed: ' + '; '.join(fails) + ')'
else: row = 'B2g "L0 count = N but total count > N, L1 jump not proportional to N, STCS control count <= N and scales with N": Confirmed'
print('MATCHED ROW:', row)
