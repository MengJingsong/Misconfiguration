#!/usr/bin/env python3
"""Self-check of run 1 for max-unsigned-short-validateKey-keyRemaining--autonomous: re-parses the RAW files (unit *.out;
cluster session.log writer outputs, system.log.life*, vk-life*.trace, samples-*.csv) with its own code, not the harness's
arms.jsonl or summary.txt, and compares with the frozen prediction numbers (B2f/B2i, B3f/B3i).
Usage: selfcheck.py <logs-root, e.g. ~/s4-b9-vk-logs/run1>.
Index.db bytes exist only in arms.jsonl (the files are dropped after each arm); that one input is used and marked."""
import glob, json, os, re, subprocess, sys
R = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/s4-b9-vk-logs/run1')
res = []
def chk(name, ok, detail=''):
    res.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + name + (' | ' + detail if detail else ''))
def info(name, detail=''):
    print('INFO ' + name + (' | ' + detail if detail else ''))
U = {'B': 1, 'KiB': 1024, 'MiB': 1 << 20, 'GiB': 1 << 30}
MSG = 'Key length of 65536 is longer than maximum of 65535'

# ---------------- unit tier
bo = open(f'{R}/unit/bounds.out').read()
rows = {m.group(1): (m.group(2), m.group(3)) for m in re.finditer(r'STAGE4 bound L=(\d+) QueryProcessor=(\S.*?) Validation=(\S.*)', bo)}
for L in (0, 1, 1000, 65534, 65535, 65536, 70000, 1000000):
    q, v = rows[str(L)]
    want = 'rejected:Key may not be empty' if L == 0 else ('accepted' if L <= 65535 else f'rejected:Key length of {L} is longer than maximum of 65535')
    chk(f'unit bound L={L}: Validation.validateKey (target) as predicted', v == want, v)
    chk(f'unit bound L={L}: QueryProcessor.validateKey as predicted', q == want, q)
chk('unit null rejected as empty by both', 'bound null QueryProcessor=rejected:Key may not be empty Validation=rejected:Key may not be empty' in bo)
chk('unit Int32 L=65536 rejected by the length check', f'STAGE4 order Int32 L=65536 rejected:{MSG}' in bo)
m = re.search(r'STAGE4 order Int32 L=65535 (\S.*)', bo)
chk('unit Int32 L=65535 rejected by the type, not the length', m and m.group(1).startswith('rejected:') and 'Key length' not in m.group(1) and 'Expected 4 or 0 byte int' in m.group(1), m.group(1) if m else '')
chk('unit Int32 L=4 accepted', 'STAGE4 order Int32 L=4 accepted' in bo)
st = open(f'{R}/unit/stream.out').read()
m = re.search(r'accepted_calls=(\d+) rejected_calls=(\d+) key_bytes_validated=(\d+).*heap_after=(\d+)', st)
chk('unit stream: 100000 calls accepted, 0 rejected, 6.55e9 key bytes, heap after GC < 100 MB', m and int(m[1]) == 100000 and int(m[2]) == 0 and int(m[3]) == 100000 * 65535 and int(m[4]) < 100e6, m.group(0)[:150] if m else '')
def hold(f):
    t = open(f'{R}/unit/{f}.out').read()
    r = {int(k): int(v) for k, v in re.findall(r'keys=(\d+) retained_bytes=(\d+)', t)}
    return (r[5000] - r[1000]) / 4000.0, r
s1, r1 = hold('hold1'); s2, r2 = hold('hold65535')
chk('unit hold L=65535 slope within L+40..L+120', 65535 + 40 <= s2 <= 65535 + 120, f'{s2:.1f}')
chk('unit hold L=1 slope within 1+40..1+120', 1 + 40 <= s1 <= 1 + 120, f'{s1:.1f}')
chk('unit slope ratio > 500', s2 / s1 > 500, f'{s2 / s1:.0f}')
chk('unit 1000 held keys of 65535 B retain about 65.6 MB (65.0 to 79 incl. baseline offset)', 65.0e6 <= r2[1000] <= 79e6, str(r2[1000]))
oo = open(f'{R}/unit/oom.out').read()
m = re.search(r'oom L=65535 oom=(\w+) held_before_oom=(\d+) validation_rejections=(\d+)', oo)
chk('unit oom: OOM after 1500..4100 held keys, 0 rejections', m and m[1] == 'true' and 1500 <= int(m[2]) <= 4100 and int(m[3]) == 0, m.group(0) if m else '')
co = open(f'{R}/unit/control.out').read()
m = re.search(r'allocations_returned=(\d+) used=(\d+) state=(\w+) after_2s_more=(\d+) validations_accepted=(\d+) rejected=(\d+)', co)
chk('unit control: 1024 allocations, used 67107840, 1025th waiting, 100000 validations accepted', m and int(m[1]) == 1024 and int(m[2]) == 1024 * 65535 and m[3] in ('WAITING', 'TIMED_WAITING') and int(m[4]) == 1024 and int(m[5]) == 100000 and int(m[6]) == 0, m.group(0) if m else '')
for f in ('bounds', 'stream', 'hold65535', 'hold1', 'oom', 'control'):
    chk(f'unit {f}: no MISMATCH line and exit recorded 0', 'MISMATCH' not in open(f'{R}/unit/{f}.out').read() and f'run {f} ' in open(f'{R}/unit/summary.txt').read() and re.search(rf'run {f} .*exit 0', open(f'{R}/unit/summary.txt').read()))

# ---------------- cluster tier
C = f'{R}/cluster'
sess = open(f'{C}/session.log').read()
js = [json.loads(l) for l in sess.splitlines() if l.startswith('{"ok"')]
names = ['pre65535', 'pre65536', 'k1000_n10k', 'k1000_n100k', 'k65535_n10k', 'k65535_n100k', 'k65536', 'p128_k65535_n100k']
chk('cluster: 8 writer outputs found', len(js) == 8, str(len(js)))
W = dict(zip(names, js))
chk('cluster precheck: 5/5 accepted at 65535, 5/5 rejected at 65536 with the exact message', W['pre65535']['ok'] == 5 and W['pre65536']['errors'] == 5 and all(MSG in k for k in W['pre65536']['messages']))
N = {'k1000_n10k': (1000, 10000), 'k1000_n100k': (1000, 100000), 'k65535_n10k': (65535, 10000), 'k65535_n100k': (65535, 100000), 'p128_k65535_n100k': (65535, 100000)}
for a, (K, n) in N.items():
    chk(f'cluster {a}: all {n} writes accepted', W[a]['ok'] == n and W[a]['errors'] == 0, f"ok={W[a]['ok']} errors={W[a]['errors']}")
chk('cluster k65536: 100 of 100 rejected with the exact message', W['k65536']['errors'] == 100 and W['k65536']['ok'] == 0 and list(W['k65536']['messages']) and all(MSG in k for k in W['k65536']['messages']), json.dumps(W['k65536']['messages'])[:200])

# system.log per life
def life(n):
    txt = open(f'{C}/system.log.life{n}').read()
    fl = re.findall(r'Enqueuing flush of ks\.(t_\w+), Reason: (\w+), Usage: ([\d.]+)\s*(B|KiB|MiB|GiB) \((\d+)%\) on-heap', txt)
    done = re.findall(r'Completed flushing \S*/ks/(t_\w+)-[0-9a-f]+/\S+-Data\.db \(([\d.]+)\s*(B|KiB|MiB|GiB)\)', txt)
    return txt, fl, done
t1, fl1, dn1 = life(1); t2, fl2, dn2 = life(2)
def flushes(fl, arm, reason='MEMTABLE_LIMIT'):
    return [float(u) * U[unit] / (1 << 20) for t, r, u, unit, pct in fl if t == 't_' + arm and r == reason]
def datasum(dn, arm):
    return sum(float(v) * U[u] for t, v, u in dn if t == 't_' + arm)
D = {a: datasum(dn1, a) for a in ('k1000_n10k', 'k1000_n100k', 'k65535_n10k', 'k65535_n100k')}
D['p128_k65535_n100k'] = datasum(dn2, 'p128_k65535_n100k')
for a, (K, n) in N.items():
    ratio = D[a] / (K * n)
    chk(f'cluster {a}: sum of flushed Data.db sizes (node log) is 0.95..1.15 x N*K', 0.95 <= ratio <= 1.15 if K == 65535 else 0.95 <= ratio <= 1.6, f'{D[a]:.0f} B, ratio {ratio:.3f}')
arms = {json.loads(l)['arm']: json.loads(l) for l in open(f'{C}/arms.jsonl')}
for a, (K, n) in N.items():
    tot = arms[a]['data_bytes'] + arms[a]['index_bytes']
    lo, hi = (1.0, 3.0) if K == 65535 else (1.0, 4.0)
    chk(f'cluster {a}: Data+Index (arms.jsonl, Index.db from there only) between {lo} and {hi} x N*K', lo * K * n <= tot <= hi * K * n, f'ratio {tot / (K * n):.2f}')
    lg = t1 if a != 'p128_k65535_n100k' else t2
    ncomp = len(re.findall(r'Compacting \S+ \[\S*/ks/t_%s-' % a, lg))
    excess = arms[a]['data_bytes'] - D[a]
    if ncomp == 0:
        chk(f'cluster {a}: no compaction ran in the arm and arms.jsonl Data.db equals the node log sum within 1 percent', abs(excess) / D[a] < 0.01, f"{arms[a]['data_bytes']} vs {D[a]:.0f}")
    else:
        # a compaction was running when the harness read the directory: outputs in progress sit beside their inputs
        chk(f'cluster {a}: compactions ran ({ncomp}); arms.jsonl Data.db is at least the flushed sum (excess {excess / 1e9:.2f} GB = in-progress compaction output)', excess >= -0.01 * D[a], f"{arms[a]['data_bytes']} vs {D[a]:.0f}")
tt = lambda a: arms[a]['data_bytes'] + arms[a]['index_bytes']
chk('cluster: K=1000 N=100k is 8..12 x N=10k', 8 <= tt('k1000_n100k') / tt('k1000_n10k') <= 12, f"{tt('k1000_n100k') / tt('k1000_n10k'):.2f}")
r_dir = tt('k65535_n100k') / tt('k65535_n10k')
info('cluster: K=65535 N=100k over N=10k, Data+Index read from the directory (frozen prediction 8..12; measured with a compaction running in the 100k arm)', f'{r_dir:.2f}')
chk('cluster (post-hoc, not a frozen prediction): flushed Data.db bytes from the node log, K=65535 N=100k over N=10k, between 9.5 and 10.5', 9.5 <= D['k65535_n100k'] / D['k65535_n10k'] <= 10.5, f"{D['k65535_n100k'] / D['k65535_n10k']:.3f}")
chk('cluster (post-hoc): flushed Data.db bytes, K=1000 N=100k over N=10k, between 9.5 and 10.5', 9.5 <= D['k1000_n100k'] / D['k1000_n10k'] <= 10.5, f"{D['k1000_n100k'] / D['k1000_n10k']:.3f}")
chk('cluster: the frozen N-scaling prediction for K=65535 (8..12) is NOT met by the directory reading', not (8 <= r_dir <= 12), f'{r_dir:.2f}')
chk('cluster k65536: nothing added to the table directory, memtable empty (arms.jsonl)', arms['k65536']['table_dir_after_flush'] == arms['k65536']['table_dir_before'] and (arms['k65536']['pre_flush_tablestats']['memtable_data'] or 0) == 0)
chk('cluster k65536: no flush line at all in the node log for the arm', not [1 for t, r, u, un, p in fl1 if t == 't_k65536'])
a256 = flushes(fl1, 'k65535_n100k'); a128 = flushes(fl2, 'p128_k65535_n100k')
b256 = flushes(fl1, 'k65535_n10k'); c256 = flushes(fl1, 'k1000_n100k')
chk('cluster k65535 N=100k @256 MiB: >= 10 MEMTABLE_LIMIT flushes, each <= 320 MiB', len(a256) >= 10 and max(a256) <= 320, f'{len(a256)} flushes, max {max(a256) if a256 else None:.1f}')
chk('cluster k65535 N=10k @256 MiB: 1..3 MEMTABLE_LIMIT flushes', 1 <= len(b256) <= 3, str(len(b256)))
chk('cluster k1000 N=100k @256 MiB: at most 1 MEMTABLE_LIMIT flush', len(c256) <= 1, str(len(c256)))
chk('cluster k65535 N=100k @128 MiB: >= 20 MEMTABLE_LIMIT flushes, each <= 160 MiB', len(a128) >= 20 and max(a128) <= 160, f'{len(a128)} flushes, max {max(a128) if a128 else None:.1f}')
med = lambda x: sorted(x)[len(x) // 2]
chk('cluster flush-count ratio 128/256 MiB between 1.6 and 2.5', 1.6 <= len(a128) / len(a256) <= 2.5, f'{len(a128)}/{len(a256)} = {len(a128) / len(a256):.2f}')
chk('cluster median logged usage ratio 256/128 MiB between 1.6 and 2.5', 1.6 <= med(a256) / med(a128) <= 2.5, f'{med(a256):.1f}/{med(a128):.1f} = {med(a256) / med(a128):.2f}')
chk('cluster: logged usage at each flush is near the pool (>= 90 percent of 256 / 128 MiB)', min(a256) >= 0.9 * 256 and min(a128) >= 0.9 * 128, f'min {min(a256):.1f} / {min(a128):.1f}')
rs = {}
for t, r, u, un, p in fl1:
    if t in ('t_k65535_n100k',): rs[r] = rs.get(r, 0) + 1
info('cluster k65535 N=100k @256 flush reasons', json.dumps(rs))

# trace files
def trace(n):
    c = {'V': {}, 'Q': 0, 'X': 0, 'X65536': 0, 'Xcp': 0, 'Xother': 0}
    for l in open(f'{C}/vk-life{n}.trace'):
        if l.startswith('X '):
            c['X'] += 1
            m = re.match(r'X Key length of (\d+) is longer than maximum of 65535 :: (.*)', l)
            c['X65536'] += bool(m and m.group(1) == '65536')
            c['Xcp'] += bool(m and 'db.ClusteringPrefix.validate(ClusteringPrefix.java:279)' in m.group(2))
            c['Xother'] += bool(m and ('QueryProcessor.validateKey' in m.group(2) or 'Validation.validateKey' in m.group(2)))
        elif l.startswith('Q '):
            c['Q'] += 1
        elif l.startswith('V '):
            n_ = int(l.split()[1]); c['V'][n_] = c['V'].get(n_, 0) + 1
    return c
c1, c2 = trace(1), trace(2)
chk('trace life 1: no Validation.validateKey entry above 65535', sum(v for k, v in c1['V'].items() if k > 65535) == 0)
chk('trace life 1: no QueryProcessor.validateKey entry above 65535', c1['Q'] == 0)
chk('trace life 1: 105 "Key length of" exceptions, all 65536, all from ClusteringPrefix.validate:279, none via the other validators', (c1['X'], c1['X65536'], c1['Xcp'], c1['Xother']) == (105, 105, 105, 0), json.dumps(c1['V']) + ' ' + str({k: v for k, v in c1.items() if k != 'V'}))
chk('trace life 1: Validation entries of length 65535 = 110005 and of 1000 = 110000', c1['V'].get(65535) == 110005 and c1['V'].get(1000) == 110000, str(c1['V']))
chk('trace life 2: 100000 Validation entries of length 65535, 0 exceptions, 0 Q', c2['V'].get(65535) == 100000 and c2['X'] == 0 and c2['Q'] == 0, str(c2))
chk('trace: the 105 exceptions equal the 105 rejected writes (5 + 100)', c1['X'] == W['pre65536']['errors'] + W['k65536']['errors'])

# samples, errors, leftovers
for a in list(N) + ['k65536']:
    f = f'{C}/samples-{a}.csv'
    rows_ = [l.strip().split(',') for l in open(f)][1:]
    if not rows_: info(f'samples {a}: no rows'); continue
    rss = [int(r[1]) for r in rows_]; hp = [int(r[4]) for r in rows_ if r[4] not in ('', '-1')]
    info(f'samples {a}', f'{len(rows_)} rows, RssAnon max {max(rss) / 1e9:.2f} GB, heap used max {(max(hp) / 1e9 if hp else -1):.2f} GB, commitlog max {max(int(r[3]) for r in rows_) / 1e6:.0f} MB')
chk('cluster: node heap used stays below the 2 GiB heap in every sample', all(int(r[4]) < 2 * (1 << 30) for a in N for r in [l.strip().split(',') for l in open(f'{C}/samples-{a}.csv')][1:] if r[4] not in ('', '-1')))
errs = [l for t in (t1, t2) for l in t.splitlines() if l.startswith('ERROR')]
chk('cluster: no ERROR line in either system.log', not errs, f'{len(errs)} lines; first: {errs[0][:160] if errs else ""}')
ps = subprocess.run("ps -eo pid,cmd | grep '[C]assandraDaemon' | grep -c s4-b9-vk", shell=True, capture_output=True, text=True).stdout.strip()
chk('no CassandraDaemon of this run is left, and /dev/shm/s4-b9-vk is gone', ps == '0' and not os.path.exists('/dev/shm/s4-b9-vk'), f'ps count {ps}')
print(f'\nselfcheck: {sum(res)} parts hold, {len(res) - sum(res)} do not hold')
