#!/usr/bin/env python3
"""Self-check of run 1 for max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous: re-parses the RAW files (unit *.out;
cluster session.log writer outputs, system.log.life*, samples-*.csv) with its own code and its own re-implementation of the B2i.2 rule,
and compares with the frozen prediction numbers (B2f/B2i, B3f/B3i). Usage: selfcheck.py <logs-root, e.g. ~/s4-b9-cp-logs/run1>.
Index.db bytes exist only in arms.jsonl (the files are dropped after each arm); that one input is used and marked."""
import json, os, re, sys
R = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/s4-b9-cp-logs/run1')
res = []
def chk(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + (' | ' + detail if detail else ''))
def info(name, detail=''): print('INFO ' + name + (' | ' + detail if detail else ''))
U = {'B': 1, 'KiB': 1024, 'MiB': 1 << 20, 'GiB': 1 << 30}
def b(v, u): return float(v) * U[u]

# ---- unit tier: grid, own rule
def rule(sizes):
    tot = sum(s for s in sizes if s > 0)
    if any(s > 65535 for s in sizes) or tot > 65535: return f'rejected:Key length of {tot} is longer than maximum of 65535'
    return 'accepted'
g = open(f'{R}/unit/grid.out').read()
cells = dict(re.findall(r'STAGE4 cell (S=\d+,N=\d) got=(\S.*)', g))
chk('unit grid: 24 uniform cells present', len(cells) == 24, str(len(cells)))
for key, got in cells.items():
    s, n = map(int, re.match(r'S=(\d+),N=(\d)', key).groups())
    chk(f'unit grid {key}', got == rule([s] * n), got)
mixed = {'mixed 65536+1': [65536, 1], 'mixed 65535+1': [65535, 1], 'mixed 65535+0': [65535, 0], 'mixed 65535+null': [65535, -1],
         'mixed null+65536': [-1, 65536], 'mixed 1+70000': [1, 70000], 'mixed 32768+32767': [32768, 32767], 'mixed 32767+32768+1': [32767, 32768, 1],
         'S=1000,N=65': [1000] * 65, 'S=1000,N=66': [1000] * 66}
for k, sz in mixed.items():
    m = re.search(r'STAGE4 cell ' + re.escape(k) + r' got=(\S.*)', g)
    chk(f'unit grid {k}', bool(m) and m.group(1) == rule(sz), m.group(1) if m else 'missing')
chk('unit grid EMPTY and STATIC accepted', 'EMPTY=accepted STATIC=accepted' in g)
for k, sz in (('S=65535', [65535]), ('S=65536', [65536])):
    m = re.search(r'STAGE4 cell ArrayClustering ' + k + r' got=(\S.*)', g)
    chk(f'unit grid ArrayClustering {k}', bool(m) and m.group(1) == rule(sz), m.group(1) if m else 'missing')
chk('unit grid: no MISMATCH', 'MISMATCH' not in g)
st = open(f'{R}/unit/stream.out').read()
m = re.search(r'accepted=(\d+) rejected=(\d+) bytes_validated=(\d+).*heap_after=(\d+)', st)
chk('unit stream: 100000 accepted, 0 rejected, 6.55e9 bytes, heap < 100 MB', m and int(m[1]) == 100000 and int(m[2]) == 0 and int(m[3]) == 100000 * 65535 and int(m[4]) < 100e6, m.group(0)[:140] if m else '')
def series(f):
    t = open(f'{R}/unit/{f}.out').read()
    h = {int(k): int(v) for k, v in re.findall(r'series S=\d+ cap=\d+ M=(\d+) heap=(\d+)', t)}
    return h, int(re.search(r'thrown=(\d+)', t)[1])
sl = {}
for f, s in (('series1000a', 1000), ('series1000b', 1000), ('series1000c', 1000), ('series1', 1)):
    h, thrown = series(f); sl[f] = (h[100000] - h[10000]) / 90000.0
    steps = [h[10000 * (i + 1)] - h[10000 * i] for i in range(1, 10)]; mean = sum(steps) / 9
    chk(f'unit {f}: 10 samples, no throw, slope within S+40..S+200, steps within 10 percent', len(h) == 10 and thrown == 0 and s + 40 <= sl[f] <= s + 200 and all(abs(x - mean) <= 0.1 * mean for x in steps), f'slope {sl[f]:.1f}')
v = [sl['series1000' + x] for x in 'abc']
chk('unit three S=1000 slopes agree within 5 percent', (max(v) - min(v)) / min(v) < 0.05, str([round(x, 1) for x in v]))
chk('unit S=1 slope < 250 and ratio S=1000/S=1 > 5', sl['series1'] < 250 and min(v) / sl['series1'] > 5, f"{sl['series1']:.1f} ratio {min(v) / sl['series1']:.1f}")
h, thrown = series('capped')
chk('unit capped control: heap at 100k within 5 MB of heap at 10k; uncapped grew > 80 MB', abs(h[100000] - h[10000]) < 5e6 and (series('series1000a')[0][100000] - series('series1000a')[0][10000]) > 80e6, f'{h[100000] - h[10000]}')

# ---- cluster tier
sess = open(f'{R}/cluster/session.log').read()
js = [json.loads(l) for l in sess.splitlines() if l.startswith('{"ok"')]
names = ['pre65535', 'pre65536', 'pre2_ok', 'pre2_sum', 'pre2_first', 'k100_r1e5', 'k1000_r1e5', 'k1000_r1e6', 'k65535_r1e4', 'k65536_r1e4', 'p64_k65535_r1e4']
chk('cluster: 11 writer outputs found', len(js) == 11, str(len(js)))
W = dict(zip(names, js))
K = {'k100_r1e5': (100, 100000), 'k1000_r1e5': (1000, 100000), 'k1000_r1e6': (1000, 1000000), 'k65535_r1e4': (65535, 10000), 'k65536_r1e4': (65536, 10000), 'p64_k65535_r1e4': (65535, 10000)}
M65536 = 'Key length of 65536 is longer than maximum of 65535'
chk('precheck single: 5 ok at 65535; 5 rejected at 65536 with exact text', W['pre65535']['ok'] == 5 and W['pre65536']['errors'] == 5 and all(M65536 in k for k in W['pre65536']['messages']))
chk('precheck two-ck: (32768,32767) ok; (32768,32768) rejected, text 65536; (70000,10) rejected, text 70010',
    W['pre2_ok']['ok'] == 3 and W['pre2_sum']['errors'] == 3 and all(M65536 in k for k in W['pre2_sum']['messages']) and W['pre2_first']['errors'] == 3 and all('Key length of 70010 is' in k for k in W['pre2_first']['messages']))
for a in ('k100_r1e5', 'k1000_r1e5', 'k1000_r1e6', 'k65535_r1e4', 'p64_k65535_r1e4'):
    chk(f'{a}: all {K[a][1]} accepted', W[a]['ok'] == K[a][1] and W[a]['errors'] == 0)
chk('k65536: 10000 rejected, one message, exact text', W['k65536_r1e4']['errors'] == 10000 and list(W['k65536_r1e4']['messages'].values()) == [10000] and all(M65536 in k for k in W['k65536_r1e4']['messages']))
life = {a: 1 for a in K}; life['p64_k65535_r1e4'] = 2
logs = {1: open(f'{R}/cluster/system.log.life1', errors='replace').read(), 2: open(f'{R}/cluster/system.log.life2', errors='replace').read()}
def flushes(a):
    t = logs[life[a]]; tab = 't_' + a
    lim = [(m[1], b(m[4], m[5]) / (1 << 20)) for m in re.finditer(r'Enqueuing flush of ks\.' + tab + r', Reason: (\w+), Usage: ([\d.]+)(B|KiB|MiB|GiB) \(\d+%\) on-heap, ([\d.]+)(B|KiB|MiB|GiB) \(\d+%\) off-heap', t)]
    done = [b(m[1], m[2]) for m in re.finditer(r'Completed flushing \S*/' + tab + r'-\w+/\S*-Data\.db \(([\d.]+)(B|KiB|MiB|GiB)\)', t)]
    return lim, done
fl = {a: flushes(a) for a in K}
arms = {j['arm']: j for j in map(json.loads, (l for l in open(f'{R}/cluster/arms.jsonl') if '"arm": "probe"' not in l))}
tot = lambda a: arms[a]['data_bytes'] + arms[a]['index_bytes']
for a in ('k1000_r1e6', 'k65535_r1e4'):
    n, k = K[a]; data = sum(fl[a][1])
    chk(f'{a}: Data.db from the node flush log within 1.0..1.2 x N*K', n * k <= data <= 1.2 * n * k, f'{data:.0f} B, ratio {data / (n * k):.3f}')
    if a == 'k1000_r1e6':
        # four flushed sstables made STCS start a compaction before the harness measured: its partial output was counted (harness defect, section 3 of the results)
        cm = re.search(r'Compaction interrupted: Compaction\(\S+, (\d+) / (\d+) bytes\)@\S+\(ks, t_k1000_r1e6\)', logs[1])
        chk('k1000_r1e6: compaction of the 4 flushed sstables was running (input total equals flush-log sum within 0.01 percent)', bool(cm) and abs(int(cm[2]) - data) / data < 1e-4, f'{cm[1]} of {cm[2]} bytes done' if cm else 'no compaction line')
        chk('k1000_r1e6: harness Data.db minus flush-log sum is positive and below the compaction input (in-flight output)', 0 < arms[a]['data_bytes'] - data < data, f"{arms[a]['data_bytes'] - data:.0f} B extra")
        r = (data + arms[a]['index_bytes']) / (n * k)
        info(f'{a}: (flush-log Data.db + harness Index.db) / N*K', f'{r:.3f}; frozen bracket 1.0..3.0 -> ' + ('inside' if 1.0 <= r <= 3.0 else 'OUTSIDE'))
        continue
    chk(f'{a}: harness Data.db within 0.5% of the flush-log sum', abs(arms[a]['data_bytes'] - data) / arms[a]['data_bytes'] < 0.005, f"{arms[a]['data_bytes']} vs {data:.0f}")
    r = tot(a) / (n * k)
    info(f'{a}: Data+Index / N*K (Index.db from arms.jsonl)', f'{r:.3f}; Index.db / N*K = {arms[a]["index_bytes"] / (n * k):.3f}; frozen bracket 1.0..3.0 -> ' + ('inside' if 1.0 <= r <= 3.0 else 'OUTSIDE'))
chk('Data+Index order (100,1e5) < (1000,1e5) < (1000,1e6); 65535 > (1000,1e5)', tot('k100_r1e5') < tot('k1000_r1e5') < tot('k1000_r1e6') and tot('k65535_r1e4') > tot('k1000_r1e5'))
chk('k65536: table directory unchanged, memtable empty', arms['k65536_r1e4']['table_dir_after_flush'] == arms['k65536_r1e4']['table_dir_before'] and not (arms['k65536_r1e4']['pre_flush_tablestats']['memtable_data'] or 0))
lim = lambda a: [x for x in fl[a][0] if x[0] == 'MEMTABLE_LIMIT']
for a in ('k1000_r1e6', 'k65535_r1e4'):
    chk(f'{a}@256: >=1 MEMTABLE_LIMIT flush, off-heap usage <= 320 MiB', len(lim(a)) >= 1 and max(x[1] for x in lim(a)) <= 320, str([round(x[1], 1) for x in lim(a)]))
for a in ('k100_r1e5', 'k1000_r1e5'):
    chk(f'{a}@256: no MEMTABLE_LIMIT flush', len(lim(a)) == 0)
chk('k65535@64: >=1 MEMTABLE_LIMIT flush, off-heap usage <= 80 MiB', len(lim('p64_k65535_r1e4')) >= 1 and max(x[1] for x in lim('p64_k65535_r1e4')) <= 80, str([round(x[1], 1) for x in lim('p64_k65535_r1e4')]))
a_, b_ = lim('k65535_r1e4')[0][1], lim('p64_k65535_r1e4')[0][1]
chk('plateau ratio first MEMTABLE_LIMIT usage between 2.5 and 6', 2.5 <= a_ / b_ <= 6, f'{a_:.1f}/{b_:.1f} = {a_ / b_:.2f}')
chk('k1000_r1e6 (1 GB of keys) logged off-heap never above the 256 MiB pool by more than 25 percent although key bytes exceed it 3.7 fold', max(x[1] for x in lim('k1000_r1e6')) <= 320 and K['k1000_r1e6'][0] * K['k1000_r1e6'][1] > 3.5 * 256 * (1 << 20) / 1.0486, '')
for a in ('k1000_r1e5', 'k1000_r1e6', 'k65535_r1e4', 'p64_k65535_r1e4'):
    rows = [l.split(',') for l in open(f'{R}/cluster/samples-{a}.csv').read().splitlines()[1:]]
    r0, rmax = int(rows[0][1]), max(int(r[1]) for r in rows); n, k = K[a]
    info(f'{a}: RssAnon samples', f'first {r0 / 2**20:.0f} MiB, max {rmax / 2**20:.0f} MiB, growth {(rmax - r0) / 2**20:.0f} MiB, N*K {n * k / 2**20:.0f} MiB')
# ---- probe (informational)
pr = json.loads(open(f'{R}/cluster/arms.jsonl').read().splitlines()[-1])['outcomes']
chk('probe (a) plain insert rejected with exact text', M65536 in pr['a_plain_insert_65536']['outcome'])
chk('probe (b) CAS insert not rejected with "Key length" (it timed out)', 'Key length' not in pr['b_cas_insert_65536']['outcome'] and 'WriteTimeout' in pr['b_cas_insert_65536']['outcome'], pr['b_cas_insert_65536']['outcome'][:80])
chk('probe (c) slice delete accepted', pr['c_slice_delete_70000']['outcome'] == 'accepted')
chk('life 2 log has the NativeClustering.java:50 assertion', 'java.lang.AssertionError: Data size 65536 >= 65536' in logs[2] and 'NativeClustering.<init>(NativeClustering.java:50)' in logs[2])
chk('life 2 log has the flush failure "exceeded maximum of 65535 bytes: 70000" (StatsMetadata)', 'Attempted serializing to buffer exceeded maximum of 65535 bytes: 70000' in logs[2] and 'StatsMetadata$StatsMetadataSerializer.serialize' in logs[2])
first_err = re.search(r'^ERROR', logs[2], re.M)
probe_at = logs[2].find('t_probe')
chk('no ERROR line in life 1; in life 2 the first ERROR comes after the probe table was created', not re.search(r'^ERROR', logs[1], re.M) and first_err is not None and probe_at != -1 and first_err.start() > probe_at)
chk('no daemon of this run left', not [p for p in os.listdir('/proc') if p.isdigit() and os.path.exists(f'/proc/{p}/cmdline') and 'CassandraDaemon' in open(f'/proc/{p}/cmdline', errors='replace').read() and 's4-b9-cp/node' in open(f'/proc/{p}/cmdline', errors='replace').read().replace('\0', ' ')])
print(f'\n{sum(res)} hold, {len(res) - sum(res)} do not hold')
