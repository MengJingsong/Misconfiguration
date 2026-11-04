#!/usr/bin/env python3
"""Independent self-check of run 1, column_index_cache_size-indexSamples-cacheSizeThreshold (results §5).
Re-parses the raw files, not the run script's tallies: the Byteman trace (index.trace), the census files (histo/*.txt, ordered by
mtime to window each pass), the unit test's harness.out; the key cache gauges are only recorded in readings.csv (the run script's
JMX reads), so those rows are read from there and recomputed here.
usage: selfcheck.py <run1 log dir> <unit log dir>     prints one line per check and a total; exit 1 if any check fails."""
import csv, glob, os, re, sys

D, U = sys.argv[1], sys.argv[2]
K = 8 * 1024 * 1024
fails = 0; n_checks = 0


def check(name, cond, detail=''):
    global fails, n_checks
    n_checks += 1
    if not cond:
        fails += 1
    print(f'{"ok  " if cond else "FAIL"} {name} {detail}')


def vint(v):
    # Cassandra unsigned vint length: 1 byte < 2^7, 2 < 2^14, 3 < 2^21, ...
    n = 1
    while v >= (1 << (7 * n)) and n < 9:
        n += 1
    return n


# ---------------- unit tier
uo = open(os.path.join(U, 'harness.out')).read().splitlines()
uc = [l for l in uo if l.startswith('STAGE4 check')]
check('unit: harness checks present and all ok', len(uc) > 500 and all(l.endswith(' ok') for l in uc), f'{len(uc)} checks')
rows = [dict(re.findall(r'(\w+)=(\S+)', l)) for l in uo if l.startswith('STAGE4 row')]
for r in rows:
    n, tw, S = int(r['n']), int(r['tw']), int(r['S'])
    check(f'unit write n={n} tw={tw}', (r['write_class'] == 'IndexedEntry') == (S <= tw and n > 1), f'S={S} class={r["write_class"]}')
reads = [dict(re.findall(r'(\w+)=(\S+)', l)) for l in uo if l.startswith('STAGE4 read')]
bad = [r for r in reads if (r['read_class'] == 'IndexedEntry') != (int(r['size']) <= int(r['tr']))]
check('unit read: class iff size <= tr for every (n, tw, tr)', len(reads) == 96 and not bad, f'{len(reads)} reads, {len(bad)} wrong')
sw = {r['read_weight'] for r in reads if r['read_class'] == 'ShallowIndexedEntry'} | {r['write_weight'] for r in rows if r['write_class'] == 'ShallowIndexedEntry'}
check('unit: one shallow weight', len(sw) == 1, str(sw))
iw = sorted({(int(r['n']), int(r['read_weight'])) for r in reads if r['read_class'] == 'IndexedEntry'})
slopes = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(iw, iw[1:])]
check('unit: read-path IndexedEntry weight linear in n (slope spread <= 1 B/block)', max(slopes) - min(slopes) <= 1.0, f'{iw} slopes {slopes}')
bl = [dict(re.findall(r'(\w+)=(\S+)', l)) for l in uo if l.startswith('STAGE4 boundary')]
nw = max(int(b['n']) for b in bl if int(b['S']) <= 2048); nr = max(int(b['n']) for b in bl if int(b['size']) <= 2048)
check('unit boundary: write class flips after nw, read class after nr', all((b['write_class'] == 'IndexedEntry') == (int(b['n']) <= nw) and
      (b['read_class'] == 'IndexedEntry') == (int(b['n']) <= nr) for b in bl), f'nw={nw} nr={nr}')

# ---------------- cluster: trace
KEY = re.compile(r'key=DecoratedKey\((-?\d+), ([0-9a-f]+)\)')
tr = []
for l in open(os.path.join(D, 'index.trace')):
    l = l.rstrip('\n')
    d = dict(re.findall(r'(\w+)=(\S+)', KEY.sub('', l)))
    m = KEY.search(l)
    if m:
        d['pk'] = int(m.group(2), 16)
    d['kind'] = l.split(' ', 1)[0]
    d['ms'] = int(d.get('ms', 0))
    tr.append(d)
writes = {}
for d in tr:
    if d['kind'] == 'write':
        writes.setdefault((d['tbl'], d['pk']), []).append(d)
CLS = {'C1': (range(1, 2001), 1024), 'CB': (range(5001, 5022), None), 'C2': (range(10001, 10501), 8192), 'C3': (range(20001, 20101), 65536),
       'C4': (range(30001, 30017), 524288)}
W = {}
for name, (pks, target) in CLS.items():
    ls = [writes.get(('t', p), []) for p in pks]
    check(f'dataset {name}: exactly one write line per partition', all(len(x) == 1 for x in ls), f'{sum(len(x) for x in ls)} lines / {len(pks)}')
    for p, x in zip(pks, ls):
        if x:
            W[p] = (int(x[0]['n']), int(x[0]['S']), x[0]['class'], int(x[0]['T']))
    ns = {W[p][0] for p in pks if p in W}; ss = sorted({W[p][1] for p in pks if p in W})
    if target:
        check(f'dataset {name}: one n, S spread <= 1 %, S within x2 of target', len(ns) == 1 and ss[-1] - ss[0] <= 0.01 * ss[0] and target / 2 <= ss[0] and ss[-1] <= 2 * target,
              f'n {ns} S {ss[0]}..{ss[-1]}')
    wrong = [p for p in pks if p in W and (W[p][2] == 'IndexedEntry') != (W[p][1] <= W[p][3] and W[p][0] > 1)]
    check(f'write path at load {name}: IndexedEntry iff S <= T', not wrong, f'T {sorted({W[p][3] for p in pks if p in W})} wrong {wrong[:5]}')

# ---------------- cluster: passes, windowed by census file mtimes
hist = sorted(glob.glob(os.path.join(D, 'histo', '*.txt')), key=os.path.getmtime)


def census(f):
    out = {}
    for l in open(f):
        p = l.split()
        if len(p) >= 4 and p[0].endswith(':'):
            out[p[3]] = (int(p[1]), int(p[2]))
    g = lambda c: out.get('org.apache.cassandra.io.sstable.' + c, (0, 0))
    return dict(indexed=g('format.big.RowIndexEntry$IndexedEntry')[0], shallow=g('format.big.RowIndexEntry$ShallowIndexedEntry')[0],
                indexinfo=g('IndexInfo')[0], indexinfo_bytes=g('IndexInfo')[1])


rc = {}
for r in csv.DictReader(open(os.path.join(D, 'readings.csv'))):
    if r['arm'] != 'idle':
        rc[(r['arm'], int(r['T']) // 1024, r['class'])] = r
prev = 0
passes = {}
shallow_w = set()
for f in hist:
    mt = int(os.path.getmtime(f) * 1000)
    tag = os.path.basename(f)[:-4]
    m = re.match(r'(sweep|flip|large)-(\d+)k-(\w+)$', tag)
    win = [d for d in tr if prev < d['ms'] <= mt]
    prev = mt
    if not m or m.group(3) not in CLS:
        continue
    arm, tk, name = m.group(1), int(m.group(2)), m.group(3)
    T = tk * 1024
    pks = set(CLS[name][0])
    disk = [d for d in win if d['kind'] == 'read' and d.get('tbl') == 't' and d.get('src') == 'disk' and d.get('pk') in pks]
    fetch = [d for d in win if d['kind'] == 'fetch' and '/ks1/t-' in d.get('path', '')]
    mism = [d for d in disk if (d['class'] == 'IndexedEntry') != (int(d['size']) <= T) or int(d['T']) != T]
    hbad = [d for d in disk if int(d['size']) - W[d['pk']][1] != 12 + 1 + vint(W[d['pk']][0])]
    tg = f'{arm} T={T} {name}'
    check(f'{tg}: a disk read line for every partition, each on the branch size <= T', {d['pk'] for d in disk} == pks and not mism,
          f'{len({d["pk"] for d in disk})}/{len(pks)}, mismatches {len(mism)}')
    check(f'{tg}: size - S = 12 + vint(headerLength=1 B) + vint(n) on every disk line', not hbad, f'{len(hbad)} off')
    cs = census(f)
    nidx = sum(d['class'] == 'IndexedEntry' for d in disk); nsh = len(disk) - nidx
    r = rc.get((arm, tk, name))
    passes[(arm, tk, name)] = dict(cs=cs, nidx=nidx, nsh=nsh, r=r)
    if nsh == 0 and nidx:
        check(f'{tg} indexed: no fetch line', not fetch, f'{len(fetch)}')
        if name == 'CB':
            # n differs per partition (60..80) and the whole class fits in K: every entry stays cached, so IndexInfo = sum of n
            sn = sum(W[p][0] for p in pks)
            check(f'{tg} indexed: live IndexInfo = sum of n over the 21 cached entries', cs['indexinfo'] == sn and cs['indexed'] == len(pks), f'{cs["indexinfo"]} vs {sn}, IndexedEntry {cs["indexed"]}')
        else:
            n = W[next(iter(pks))][0]
            check(f'{tg} indexed: live IndexInfo = n x live IndexedEntry', cs['indexinfo'] == n * cs['indexed'], f'{cs["indexinfo"]} vs {n} x {cs["indexed"]}')
        if r and int(r['capacity']) == K and name != 'CB':   # CB's demand (21 entries, ~0.28 MB) is below K: the re-cap form does not apply
            ea, sa = int(r['entries_after']), int(r['size_after'])
            check(f'{tg} indexed: K - w <= Size <= K and Entries < P', K - 1.05 * sa / ea <= sa <= K and ea < len(pks), f'Size {sa} Entries {ea}')
            check(f'{tg} indexed: census IndexedEntry within 50 of Entries', cs['indexed'] <= ea and ea - cs['indexed'] <= 50, f'{cs["indexed"]} vs {ea}')
    elif nidx == 0 and nsh:
        reads_with_fetch = len({d['ms'] for d in fetch})
        check(f'{tg} shallow: fetch lines >= P', len(fetch) >= len(pks), f'{len(fetch)}')
        check(f'{tg} shallow: live ShallowIndexedEntry >= P', cs['shallow'] >= len(pks), f'{cs["shallow"]}')
        if r:
            de = int(r['entries_after']) - int(r['entries_before']); ds = int(r['size_after']) - int(r['size_before'])
            check(f'{tg} shallow: Entries + P', de == len(pks), f'{de}')
            if de:
                shallow_w.add(ds / de)
    else:
        print(f'info {tg}: mixed, indexed {nidx} shallow {nsh}')
check('every shallow pass adds the same Size per entry', len(shallow_w) == 1, str(shallow_w))

# CB boundary at 2 KiB on the node: both sites
cb = passes.get(('sweep', 2, 'CB'))
cbl = [d for d in tr if d['kind'] == 'read' and d.get('src') == 'disk' and d.get('pk') in set(CLS['CB'][0]) and d.get('T') == '2048']
pairs = sorted((W[d['pk']][0], W[d['pk']][1], int(d['size']), W[d['pk']][2], d['class']) for d in cbl)
print('info CB at 2 KiB (n, S, size, write class, read class):', pairs)
check('CB at 2 KiB: write class iff S <= 2048 and read class iff size <= 2048', all((p[3] == 'IndexedEntry') == (p[1] <= 2048) and (p[4] == 'IndexedEntry') == (p[2] <= 2048) for p in pairs) and len(pairs) >= 21)

# arm W
ww = {d['pk']: d for d in tr if d['kind'] == 'write' and d.get('tbl') == 'w'}
check('arm W: pk 1-5 IndexedEntry at T=16384, pk 6-10 Shallow at T=2048', sorted(ww) == list(range(1, 11)) and
      all(ww[p]['class'] == 'IndexedEntry' and ww[p]['T'] == '16384' for p in range(1, 6)) and all(ww[p]['class'] == 'ShallowIndexedEntry' and ww[p]['T'] == '2048' for p in range(6, 11)))
check('ks1.t written only at load', len([1 for (t, p) in writes if t == 't']) == sum(len(CLS[c][0]) for c in CLS))

# large cache
lg = passes.get(('large', 256, 'C3'))
if lg and lg['r']:
    r = lg['r']
    de = int(r['entries_after']) - int(r['entries_before'])
    check('large cache C3 at 256 KiB: 100 entries added, all indexed, IndexInfo = 2000 x IndexedEntry', de == 100 and lg['nidx'] == 100 and lg['cs']['indexinfo'] == 2000 * lg['cs']['indexed'],
          f'+{de} indexed {lg["nidx"]} census {lg["cs"]}')

print(f'TOTAL {n_checks} checks, {fails} failed')
sys.exit(1 if fails else 0)
