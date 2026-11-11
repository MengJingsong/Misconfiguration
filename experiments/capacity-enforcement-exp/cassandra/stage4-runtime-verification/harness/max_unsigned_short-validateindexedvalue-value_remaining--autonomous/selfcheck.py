#!/usr/bin/env python3
"""selfcheck.py <logs-dir-of-the-run>   (e.g. ~/s4-b2-logs/run1-a)
Independent re-parse of the raw files of run 1 for max_unsigned_short-validateindexedvalue-value_remaining--autonomous.
It does not import analyze-unit.py or cluster-run.py; it reads unit/*.out, cluster/arms.jsonl, cluster/system.log.life{1,2}, cluster/summary.txt
and prints one line per part: 'HOLDS' / 'DOES NOT HOLD' with the numbers."""
import json, re, sys, os, collections
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
# ---- unit: boundary (raw lines)
res = {}
for l in lines(f'{R}/unit/bounds.out'):
    m = re.match(r'STAGE4 bound path=(\S+) indexed=(\S+) S=(\d+) result=(.*)', l)
    if m: res[(m.group(1), m.group(2), int(m.group(3)))] = m.group(4)
for s in (1000, 65533, 65534):
    part(f'unit regular indexed S={s} accepted', res.get(('regular', 'yes', s)) == 'accepted')
for s in (65535, 65536):
    v = res.get(('regular', 'yes', s), '')
    part(f'unit regular indexed S={s} rejected, message names size {s} and max 65535', v.startswith('rejected') and f'Cannot index value of size {s} for index' in v and '(maximum allowed size=65535)' in v, v[:120])
part('unit unindexed S=65535 and 65536 accepted (the index check, not another validator, rejects)', res.get(('regular', 'no', 65535)) == 'accepted' and res.get(('regular', 'no', 65536)) == 'accepted')
v = res.get(('clustering', 'yes', 65535), '')
part('unit clustering indexed 65535 rejected by the index check; 65534 accepted; unindexed 65535 accepted',
     'Cannot index value of size 65535' in v and res.get(('clustering', 'yes', 65534)) == 'accepted' and res.get(('clustering', 'no', 65535)) == 'accepted', v[:100])
# ---- unit: scale
def scale(f):
    d = {}
    for l in lines(f'{R}/unit/{f}.out'):
        if l.startswith('STAGE4 scale '):
            x = dict(re.findall(r'(\w+)=(\S+)', l))
            d[(x['indexed'], int(x['N']))] = {k: (int(v) if re.fullmatch(r'-?\d+', v) else v) for k, v in x.items()}
    return d
sd, sp = scale('scale_default'), scale('scale_pool64')
if all(('yes', n) in sd for n in (100, 1000, 4000)):
    ids = [sd[('yes', n)]['idx_disk'] for n in (100, 1000, 4000)]
    ns = [sd[('yes', n)]['NxS'] for n in (100, 1000, 4000)]
    part('unit index disk bytes grow with N (100 < 1000 < 4000) and each is 0.9..2.2 x N*S', ids[0] < ids[1] < ids[2] and all(0.9 * a <= b <= 2.2 * a for a, b in zip(ns, ids)), f'ids={ids} ratios={[round(b / a, 2) for a, b in zip(ns, ids)]}')
    part('unit ratio 4000/1000 in [3.5,4.5] and 1000/100 in [8,12]', 3.5 <= ids[2] / ids[1] <= 4.5 and 8 <= ids[1] / ids[0] <= 12, f'{ids[2] / ids[1]:.2f} {ids[1] / ids[0]:.2f}')
    part('unit no rejected rows at any N', all(sd[('yes', n)]['rejected'] == 0 for n in (100, 1000, 4000)))
    a = sd[('yes', 4000)]; b = sd[('no', 4000)]
    part('unit base table bytes within 5% of the unindexed table; the index adds >= 0.9 N*S', abs(a['base_disk'] - b['base_disk']) <= 0.05 * b['base_disk'] and a['idx_disk'] >= 0.9 * a['NxS'], f"{a['base_disk']} {b['base_disk']} {a['idx_disk']}")
    part('unit default-pool arm: no memtable flush before the explicit flush', a['idx_sstables_before_flush'] == 0 and a['base_sstables_before_flush'] == 0)
    c = sp.get(('yes', 4000))
    if c:
        part('unit 64 MiB pool: flushes happened before the explicit one, peak pool usage <= 160 MiB, default arm peak > 2x', c['idx_sstables_before_flush'] >= 1 and c['peak_pool_onheap'] <= 160 * MiB and a['peak_pool_onheap'] > 2 * c['peak_pool_onheap'],
             f"idx_sst={c['idx_sstables_before_flush']} peak64={c['peak_pool_onheap'] / MiB:.1f} MiB default={a['peak_pool_onheap'] / MiB:.1f} MiB")
        part('unit 64 MiB pool: the index still holds the same bytes (idx disk 0.9..2.2 x N*S, no rejections)', c['rejected'] == 0 and 0.9 * c['NxS'] <= c['idx_disk'] <= 2.2 * c['NxS'], f"{c['idx_disk'] / c['NxS']:.2f}")
    else: part('unit pool64 arm present', False)
else: part('unit scale arms present', False)
# ---- cluster
arms = {}
for l in lines(f'{R}/cluster/arms.jsonl'):
    j = json.loads(l); arms[j['arm']] = j
def units(v, u): return float(v) * {'B': 1, 'KiB': 1024, 'MiB': MiB, 'GiB': 1 << 30, 'TiB': 1 << 40}[u]
def node_log(life):
    """per table: (flush lines MEMTABLE_LIMIT with off-heap MiB, Data.db bytes of base and of the index dir from 'Completed flushing')"""
    ml = collections.defaultdict(list); base = collections.Counter(); idx = collections.Counter()
    for l in lines(f'{R}/cluster/system.log.life{life}'):
        m = re.search(r'Enqueuing flush of (\S+), Reason: (\w+), Usage: .*?([\d.]+)(B|KiB|MiB|GiB)\s*\(\d+%\) off-heap', l)
        if m and m.group(2) == 'MEMTABLE_LIMIT': ml[m.group(1)].append(units(m.group(3), m.group(4)) / MiB)
        m = re.search(r'Completed flushing /dev/shm/s4-b2/node/data/ks/(t_\w+?)-[0-9a-f]{32}/(\.idx_\w+?/)?nb-\d+-big-Data\.db \(([\d.]+)(B|KiB|MiB|GiB)\)', l)
        if m: (idx if m.group(2) else base)[m.group(1)] += units(m.group(3), m.group(4))
    return ml, base, idx
ml1, b1, i1 = node_log(1); ml2, b2, i2 = node_log(2)
if arms:
    for a in ('n1000', 'n4000', 'n16000', 'noidx4000', 's100'):
        r = arms[a]; t = 't_' + a
        part(f'cluster {a}: all {r["N"]} inserts accepted', r['ok'] == r['N'] and r['errors'] == 0)
        if a not in ('noidx4000', 's100'):
            logged = i1[t]
            part(f'cluster {a}: index Data.db bytes in arms.jsonl agree with the node\'s own "Completed flushing" sizes (5%)', logged > 0 and abs(logged - r['idx_data_bytes']) <= 0.05 * logged, f"arms={r['idx_data_bytes']} log={logged:.0f}")
    k = arms['s65535']
    part('cluster s65535: all 200 rejected with the index message; nothing flushed for that table in the node log; memtable empty',
         k['errors'] == 200 and all('Cannot index value of size 65535 for index' in m for m in k['messages']) and i1['t_s65535'] == 0 and b1['t_s65535'] == 0 and (k['pre_flush_tablestats']['memtable_data'] or 0) == 0,
         f"errors={k['errors']} log base={b1['t_s65535']} idx={i1['t_s65535']}")
    idxb = {a: arms[a]['idx_data_bytes'] + arms[a]['idx_index_bytes'] for a in ('n1000', 'n4000', 'n16000', 's100')}
    NS = {a: arms[a]['N'] * arms[a]['S'] for a in idxb}
    part('cluster index bytes: 0.9..2.2 x N*S, ratios 16000/4000 and 4000/1000 in [3.5,4.5]',
         all(0.9 * NS[a] <= idxb[a] <= 2.2 * NS[a] for a in ('n1000', 'n4000', 'n16000')) and 3.5 <= idxb['n16000'] / idxb['n4000'] <= 4.5 and 3.5 <= idxb['n4000'] / idxb['n1000'] <= 4.5,
         f"{ {a: round(idxb[a] / NS[a], 2) for a in idxb} } {idxb['n16000'] / idxb['n4000']:.2f} {idxb['n4000'] / idxb['n1000']:.2f}")
    n = arms['noidx4000']
    part('cluster no-index base bytes in [0.9,1.3] x N*S; index adds >= 0.9 x N*S', 0.9 * NS['n4000'] <= n['data_bytes'] + n['index_bytes'] <= 1.3 * NS['n4000'] and idxb['n4000'] >= 0.9 * NS['n4000'], f"{n['data_bytes'] + n['index_bytes']}")
    c1, c2 = idxb['s100'] / NS['s100'], idxb['n1000'] / NS['n1000']
    part('cluster small-value control: index bytes per key byte within [0.5,2.0] x that of n1000', 0.5 <= c1 / c2 <= 2.0, f'{c1:.2f} / {c2:.2f}')
    # pool plateau from the node log, not from arms.jsonl
    f1 = ml1.get('ks.t_n16000', []); f2 = ml2.get('ks.t_p256_n16000', []) or [x for k_, v in ml2.items() if 't_p256_n16000' in k_ for x in v]
    f1 = f1 or [x for k_, v in ml1.items() if 't_n16000' in k_ and 'p256' not in k_ for x in v]
    part('cluster pool plateau (node log): >=1 MEMTABLE_LIMIT flush at 512 MiB with off-heap <= 640 MiB, >=1 at 256 MiB with <= 320 MiB, first-usage ratio in [1.4,3.0]',
         len(f1) >= 1 and len(f2) >= 1 and max(f1) <= 640 and max(f2) <= 320 and 1.4 <= f1[0] / f2[0] <= 3.0, f'512: {[round(x, 1) for x in f1]} 256: {[round(x, 1) for x in f2]}')
    p = arms.get('p256_n16000')
    sl = lambda a: (arms[a].get('post_flush_idx_tablestats') or {}).get('space_live')
    part('cluster p256_n16000: accepted all rows; the node\'s own "Space used (live)" of the index table agrees with n16000 within 5% (usage follows the data; the pool sets only the plateau)',
         bool(p) and p['errors'] == 0 and bool(sl('p256_n16000')) and abs(sl('p256_n16000') - sl('n16000')) <= 0.05 * sl('n16000'), f"{sl('p256_n16000')} vs {sl('n16000')}")
    part('cluster index "Space used (live)" (nodetool, independent of the file glob): ratios 16000/4000 and 4000/1000 in [3.5,4.5], and 0.9..2.2 x N*S',
         all(sl(a) for a in ('n1000', 'n4000', 'n16000')) and 3.5 <= sl('n16000') / sl('n4000') <= 4.5 and 3.5 <= sl('n4000') / sl('n1000') <= 4.5 and all(0.9 * NS[a] <= sl(a) <= 2.2 * NS[a] for a in ('n1000', 'n4000', 'n16000')),
         f"{ {a: sl(a) for a in ('n1000', 'n4000', 'n16000')} }")
    part('cluster s100 (655,340 rows, many flushes and background compactions): index Data+Index in arms.jsonl agrees with nodetool "Space used (live)" within 5% (the flush-log sum is not comparable here: compactions ran between the flushes and the measurement)',
         abs(arms['s100']['idx_data_bytes'] + arms['s100']['idx_index_bytes'] - sl('s100')) <= 0.05 * sl('s100'), f"{arms['s100']['idx_data_bytes'] + arms['s100']['idx_index_bytes']} vs {sl('s100')}")
    comp = [l for l in lines(f'{R}/cluster/system.log.life2') if 't_p256_n16000' in l and ('Compacting' in l or 'Compaction interrupted' in l)]
    part('cluster p256_n16000: the glob reading (3.03e9) exceeds Space used (live) (2.11e9) because compactions of that table were running at the measurement (node log shows Compacting / interrupted lines)', len(comp) >= 2 and arms['p256_n16000']['idx_data_bytes'] + arms['p256_n16000']['idx_index_bytes'] > 1.2 * sl('p256_n16000'), f'{len(comp)} compaction lines')
    print('INFO: glob Data+Index of the index dir vs nodetool Space used (live) per arm: ' + ', '.join(f"{a}={idxb.get(a, arms[a]['idx_data_bytes'] + arms[a]['idx_index_bytes'])}/{sl(a)}" for a in ('n1000', 'n4000', 'n16000', 's100', 'p256_n16000')))
    summ = '\n'.join(lines(f'{R}/cluster/summary.txt'))
    part('cluster: no daemon and no /dev/shm/s4-b2 left (summary last line)', 'node pid left: None; /dev/shm/s4-b2 exists: False' in summ)
    part('cluster: no ERROR line in either system.log', not any(l.startswith('ERROR') for life in (1, 2) for l in lines(f'{R}/cluster/system.log.life{life}')),
         ' | '.join(l[:140] for life in (1, 2) for l in lines(f'{R}/cluster/system.log.life{life}') if l.startswith('ERROR'))[:300])
    print('INFO: EXPECTED lines in summary.txt: yes=%d no=%d' % (len(re.findall(r'^EXPECTED: .* - yes', summ, re.M)), len(re.findall(r'^EXPECTED: .* - NO', summ, re.M))))
else: part('cluster arms present', False)
print(f'selfcheck: {bad} part(s) do not hold')
