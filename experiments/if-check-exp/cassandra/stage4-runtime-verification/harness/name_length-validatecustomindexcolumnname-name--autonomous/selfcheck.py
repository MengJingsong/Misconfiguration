#!/usr/bin/env python3
"""selfcheck.py <logs-dir-of-the-run>   (e.g. ~/s4-b2-logs/run1-b)
Independent re-parse of the raw files of run 1 for name_length-validatecustomindexcolumnname-name--autonomous.
Does not import analyze-unit.py or cluster-run.py; reads unit/{names,rows}.out, cluster/arms.jsonl, cluster/system.log.life{A,B,C}, cluster/summary.txt."""
import json, re, sys, statistics, collections
R = sys.argv[1]
bad = 0
def part(name, ok, detail=''):
    global bad
    if not ok: bad += 1
    print(f'{"HOLDS" if ok else "DOES NOT HOLD"}: {name}' + (f' [{detail}]' if detail else ''))
def lines(f):
    try: return open(f).read().splitlines()
    except FileNotFoundError: return []
MiB = 1 << 20
spread = lambda v: (max(v) - min(v)) / (sum(v) / len(v))
# ---- unit names
arms = collections.defaultdict(list)
for l in lines(f'{R}/unit/names.out'):
    if not l.startswith('STAGE4 arm '): continue
    head, _, msg = l.partition(' msg=')
    x = dict(re.findall(r'(\w+)=(\S+)', head))
    arms[(x['kind'], int(x['L']))].append((x, msg))
for L in (1, 47, 48):
    v = arms[('custom', L)]
    part(f'unit custom L={L}: 3 repeats accepted with all 10,000 rows stored (rejected_rows=0)', len(v) == 3 and all(x.get('result') == 'accepted' and x.get('rejected_rows') == '0' for x, _ in v))
for L in (49, 64, 200):
    v = arms[('custom', L)]
    nm = 'c' + 'x' * (L - 1)
    part(f'unit custom L={L}: CREATE INDEX rejected 3 of 3 with "Column \'<{L} chars>\' is longer than the permissible name length of 48 characters"',
         len(v) == 3 and all(x.get('create_index') == 'rejected' and f"Column '{nm}' is longer than the permissible name length of 48 characters" in m for x, m in v))
for L in (1, 47, 48, 49, 64, 200):
    v = arms[('plain', L)]
    part(f'unit plain L={L}: 3 repeats accepted, rejected_rows=0', len(v) == 3 and all(x.get('result') == 'accepted' and x.get('rejected_rows') == '0' for x, _ in v))
def med(kind, L, f): return statistics.median(int(x[f]) for x, _ in arms[(kind, L)] if f in x)
for f in ('base_owns', 'dir_bytes'):
    pl = [med('plain', L, f) for L in (1, 47, 48, 49, 64, 200)]
    cu = [med('custom', L, f) for L in (1, 47, 48)]
    part(f'unit {f}: plain six-L spread <= 1% and custom three-L spread <= 1%', spread(pl) <= 0.01 and spread(cu) <= 0.01, f'plain {spread(pl) * 100:.3f}% custom {spread(cu) * 100:.3f}%')
part('unit no step at 48: |plain(49)-plain(48)| <= 1% for owns and for directory bytes', all(abs(med('plain', 49, f) - med('plain', 48, f)) <= 0.01 * med('plain', 48, f) for f in ('base_owns', 'dir_bytes')))
part('unit absolute scale: plain memtable owns > 5 MB and directory > 5 MB for 10,000 x 100 B (the instrument sees data)', med('plain', 48, 'base_owns') > 5e6 and med('plain', 48, 'dir_bytes') > 5e6, f"{med('plain', 48, 'base_owns')} {med('plain', 48, 'dir_bytes')}")
rows = {}
for l in lines(f'{R}/unit/rows.out'):
    if l.startswith('STAGE4 arm '):
        x = dict(re.findall(r'(\w+)=(\S+)', l)); rows[(x['kind'], int(x['N']))] = x
try:
    o = [int(rows[('plain', n)]['base_owns']) for n in (1000, 10000, 100000)]
    d = [int(rows[('plain', n)]['dir_bytes']) for n in (1000, 10000, 100000)]
    part('unit row-count control: owns ratios in [7,13], directory ratios in [5,13]', all(7 <= o[i + 1] / o[i] <= 13 for i in (0, 1)) and all(5 <= d[i + 1] / d[i] <= 13 for i in (0, 1)), f'owns {o} dir {d}')
    part('unit unindexed baseline smaller than indexed', int(rows[('none', 10000)]['dir_bytes']) < d[1], f"{rows[('none', 10000)]['dir_bytes']} vs {d[1]}")
except KeyError as e:
    part('unit rows arms present', False, str(e))
# ---- cluster
rec = {}
for l in lines(f'{R}/cluster/arms.jsonl'):
    j = json.loads(l); rec.setdefault(j['arm'], []).append(j)
def units(v, u): return float(v) * {'B': 1, 'KiB': 1024, 'MiB': MiB, 'GiB': 1 << 30}[u]
def flushes(life):
    out = collections.defaultdict(list)
    for l in lines(f'{R}/cluster/system.log.life{life}'):
        m = re.search(r'Enqueuing flush of (\S+), Reason: MEMTABLE_LIMIT, Usage: ([\d.]+)(B|KiB|MiB|GiB) \(\d+%\) on-heap', l)
        if m: out[m.group(1)].append(units(m.group(2), m.group(3)) / MiB)
    return out
fA, fB, fC = flushes('A'), flushes('B'), flushes('C')
if rec:
    one = lambda a: rec[a][-1]
    for L in (49, 100):
        j = one(f'custom{L}'); nm = 'c' + 'x' * (L - 1)
        part(f'cluster custom{L}: CREATE INDEX rejected with the exact text; zero indexes in schema; nothing loaded', j['schema']['create_index'] == 'rejected' and f"Column '{nm}' is longer than the permissible name length of 48 characters" in j['schema']['message'] and j['index_in_schema'] == 0 and not fA.get('ks.t_custom%d' % L))
    for a in ('custom40', 'custom48', 'plain40', 'plain48', 'plain100', 'none40'):
        j = one(a)
        part(f'cluster {a}: DDL accepted, {j["N"]} rows accepted, 0 errors', j['schema']['create_index'] in ('ok', 'none') and j['ok'] == j['N'] and j['errors'] == 0 and j['N'] >= 500000, f"N={j['N']}")
    dc = {a: one(a)['dir_after_compact'] for a in ('plain40', 'plain48', 'plain100', 'custom40', 'custom48', 'none40')}
    part('cluster directory bytes after compaction: plain 40/48/100 spread <= 2%; custom 40 vs 48 <= 2%; none40 < plain40',
         spread([dc['plain40'], dc['plain48'], dc['plain100']]) <= 0.02 and spread([dc['custom40'], dc['custom48']]) <= 0.02 and dc['none40'] < dc['plain40'],
         f"plain {spread([dc['plain40'], dc['plain48'], dc['plain100']]) * 100:.3f}% custom {spread([dc['custom40'], dc['custom48']]) * 100:.3f}% {dc}")
    fa = {a: fA.get('ks.t_' + a, []) for a in ('plain40', 'plain48', 'plain100')}
    part('cluster node log: each plain arm has >=1 MEMTABLE_LIMIT flush; first logged on-heap usage spread <= 15%', all(len(v) >= 1 for v in fa.values()) and spread([v[0] for v in fa.values()]) <= 0.15, str({k: [round(x, 1) for x in v[:3]] + ['...%d' % len(v)] for k, v in fa.items()}))
    cB, cC = fB.get('ks.t_plain48', []), fC.get('ks.t_plain48', [])
    part('cluster pool control from the node log: first usage 512 MiB over 128 MiB in [2.5,6]; flush count at 128 > at 512 >= 1', len(cB) > len(cC) >= 1 and 2.5 <= cC[0] / cB[0] <= 6, f'128: first {cB[:1]} n={len(cB)}; 512: first {cC[:1]} n={len(cC)}; 256 n={len(fa["plain48"])}')
    ds = [one('plain48')['dir_after_compact']] + [x[-1]['dir_after_compact'] for k, x in rec.items() if k == 'plain48']
    allp = [j['dir_after_compact'] for j in rec['plain48']]
    part('cluster plain48 repeated across lives (128/256/512 MiB): directory bytes after compaction spread <= 2%', len(allp) == 3 and spread(allp) <= 0.02, str(allp))
    summ = '\n'.join(lines(f'{R}/cluster/summary.txt'))
    part('cluster: no daemon and no /dev/shm/s4-b2 left (summary last line)', 'node pid left: None; /dev/shm/s4-b2 exists: False' in summ)
    errs = [l[:140] for life in 'ABC' for l in lines(f'{R}/cluster/system.log.life{life}') if l.startswith('ERROR')]
    part('cluster: no ERROR line in any system.log', not errs, ' | '.join(errs)[:300])
    print('INFO: EXPECTED lines in summary.txt: yes=%d no=%d' % (len(re.findall(r'^EXPECTED: .* - yes', summ, re.M)), len(re.findall(r'^EXPECTED: .* - NO', summ, re.M))))
else:
    part('cluster arms present', False)
print(f'selfcheck: {bad} part(s) do not hold')
