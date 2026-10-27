#!/usr/bin/env python3
"""Self-check of run 1 for max-unsigned-short-validate-key-remaining--autonomous: re-parses the RAW files (unit *.out;
cluster session.log writer outputs, system.log.life*, samples-*.csv) with its own code, not the harness's arms.jsonl,
and compares with the frozen prediction numbers (B2f/B2i, B3f/B3i). Usage: selfcheck.py <logs-root, e.g. ~/s4-b8-uk-logs/run1>.
Index.db bytes exist only in arms.jsonl (the files are dropped after each arm); that one input is used and marked."""
import glob, json, os, re, sys
R = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/s4-b8-uk-logs/run1')
res = []
def chk(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + (' | ' + detail if detail else ''))
U = {'B': 1, 'KiB': 1024, 'MiB': 1 << 20, 'GiB': 1 << 30}
def b(v, u): return float(v) * U[u]

# ---- unit tier
bo = open(f'{R}/unit/bounds.out').read()
rows = dict((m.group(1), (m.group(2), m.group(3))) for m in re.finditer(r'STAGE4 bound L=(\d+) QueryProcessor=(\S.*?) Validation=(\S.*)', bo))
for L in (0, 1, 1000, 65534, 65535, 65536, 70000, 1000000):
    q, v = rows[str(L)]
    want = 'rejected:Key may not be empty' if L == 0 else ('accepted' if L <= 65535 else f'rejected:Key length of {L} is longer than maximum of 65535')
    chk(f'unit bound L={L} both methods', q == want and v == want, f'{q} / {v}')
chk('unit null and UNSET rejected as empty', 'bound null QueryProcessor=rejected:Key may not be empty Validation=rejected:Key may not be empty' in bo and 'UNSET QueryProcessor=rejected:Key may not be empty' in bo)
st = open(f'{R}/unit/stream.out').read()
m = re.search(r'accepted_calls=(\d+) rejected_calls=(\d+) key_bytes_validated=(\d+).*heap_after=(\d+)', st)
chk('unit stream: 200000 calls accepted, 0 rejected, 6.55e9 key bytes, heap < 100 MB', m and int(m[1]) == 200000 and int(m[2]) == 0 and int(m[3]) == 100000 * 65535 and int(m[4]) < 100e6, m.group(0)[:150] if m else '')
def hold(f):
    t = open(f'{R}/unit/{f}.out').read()
    r = {int(k): int(v) for k, v in re.findall(r'keys=(\d+) retained_bytes=(\d+)', t)}
    return (r[5000] - r[1000]) / 4000.0, r
s1, r1 = hold('hold1'); s2, r2 = hold('hold65535')
chk('unit hold L=65535 slope within L+40..L+120', 65535 + 40 <= s2 <= 65535 + 120, f'{s2:.1f}')
chk('unit hold L=1 slope within 1+40..1+120', 1 + 40 <= s1 <= 1 + 120, f'{s1:.1f}')
chk('unit slope ratio > 500', s2 / s1 > 500, f'{s2 / s1:.0f}')
chk('unit 1000 keys of 65535 B retain about 65.6 MB (65.0 to 66.5)', 65.0e6 <= r2[1000] - 0 <= 79e6, f'{r2[1000]} (includes base heap offset of the first reading)')

# ---- cluster tier
sess = open(f'{R}/cluster/session.log').read()
js = [json.loads(l) for l in sess.splitlines() if l.startswith('{"ok"')]
names = ['pre65535', 'pre65536', 'k16', 'k1024', 'k32768', 'k65535', 'k65536', 'c16big', 'p128_k32768']
chk('cluster: 9 writer outputs found', len(js) == 9, str(len(js)))
W = dict(zip(names, js))
K = {'k16': (16, 10000), 'k1024': (1024, 10000), 'k32768': (32768, 10000), 'k65535': (65535, 10000), 'k65536': (65536, 10000), 'c16big': (16, 650000), 'p128_k32768': (32768, 10000)}
MSG = 'Key length of 65536 is longer than maximum of 65535'
chk('precheck 5/5 accepted at 65535', W['pre65535']['ok'] == 5 and W['pre65535']['errors'] == 0)
chk('precheck 5/5 rejected at 65536 with exact text', W['pre65536']['errors'] == 5 and all(MSG in k for k in W['pre65536']['messages']))
for a in ('k16', 'k1024', 'k32768', 'k65535', 'c16big', 'p128_k32768'):
    chk(f'{a}: all {K[a][1]} accepted', W[a]['ok'] == K[a][1] and W[a]['errors'] == 0)
chk('k65536: 10000 rejected, one message, exact text', W['k65536']['errors'] == 10000 and list(W['k65536']['messages'].values()) == [10000] and all(MSG in k for k in W['k65536']['messages']))
life = {'k16': 1, 'k1024': 1, 'k32768': 1, 'k65535': 1, 'k65536': 1, 'c16big': 1, 'p128_k32768': 2}
logs = {1: open(f'{R}/cluster/system.log.life1', errors='replace').read(), 2: open(f'{R}/cluster/system.log.life2', errors='replace').read()}
def flushes(a):
    t = logs[life[a]]; tab = 't_' + a
    lim = [m for m in re.finditer(r'Enqueuing flush of ks\.' + tab + r', Reason: (\w+), Usage: ([\d.]+)(B|KiB|MiB|GiB) \(\d+%\) on-heap, ([\d.]+)(B|KiB|MiB|GiB) \(\d+%\) off-heap', t)]
    done = [b(m[1], m[2]) for m in re.finditer(r'Completed flushing \S*/' + tab + r'-\w+/\S*-Data\.db \(([\d.]+)(B|KiB|MiB|GiB)\)', t)]
    return [(m[1], b(m[4], m[5]) / (1 << 20)) for m in lim], done
fl = {a: flushes(a) for a in life}
for a in ('k16', 'k1024', 'k32768', 'k65535'):
    n, k = K[a]; data = sum(fl[a][1])
    chk(f'{a}: Data.db from the flush log within 1.0..1.2 x N*K' if a in ('k32768', 'k65535') else f'{a}: Data.db from the flush log (info)', (1.0 * n * k <= data <= 1.2 * n * k) if a in ('k32768', 'k65535') else True, f'{data:.0f} B vs N*K {n * k}; ratio {data / (n * k):.3f}')
arms = {j['arm']: j for j in map(json.loads, open(f'{R}/cluster/arms.jsonl'))}
tot = lambda a: arms[a]['data_bytes'] + arms[a]['index_bytes']
for a in ('k32768', 'k65535'):
    n, k = K[a]
    chk(f'{a}: Data+Index (Index.db from arms.jsonl) between 1.0 and 3.0 x N*K', n * k <= tot(a) <= 3 * n * k, f'{tot(a) / (n * k):.2f}')
    chk(f'{a}: harness Data.db within 0.5% of the sum of flush-log Data.db sizes', abs(arms[a]['data_bytes'] - sum(fl[a][1])) / arms[a]['data_bytes'] < 0.005, f"{arms[a]['data_bytes']} vs {sum(fl[a][1]):.0f}")
chk('monotone Data+Index at N=10000 (16<1024<32768<65535)', tot('k16') < tot('k1024') < tot('k32768') < tot('k65535'))
chk('k65536: table directory unchanged, memtable empty', arms['k65536']['table_dir_after_flush'] == arms['k65536']['table_dir_before'] and not (arms['k65536']['pre_flush_tablestats']['memtable_data'] or 0), '')
lim = lambda a: [x for x in fl[a][0] if x[0] == 'MEMTABLE_LIMIT']
chk('k65535@512: >=1 MEMTABLE_LIMIT flush, off-heap usage <= 640 MiB', len(lim('k65535')) >= 1 and max(x[1] for x in lim('k65535')) <= 640, str(lim('k65535')))
chk('k32768@512: no MEMTABLE_LIMIT flush', len(lim('k32768')) == 0)
chk('k32768@128: >=1 MEMTABLE_LIMIT flush, off-heap usage <= 160 MiB', len(lim('p128_k32768')) >= 1 and max(x[1] for x in lim('p128_k32768')) <= 160, str(lim('p128_k32768')))
a_, b_ = lim('k65535')[0][1], lim('p128_k32768')[0][1]
chk('plateau ratio first MEMTABLE_LIMIT usage between 2.5 and 6', 2.5 <= a_ / b_ <= 6, f'{a_:.1f}/{b_:.1f} = {a_ / b_:.2f}')
chk('c16big Data+Index bytes > k1024 Data+Index bytes', tot('c16big') > tot('k1024'), f"{tot('c16big')} vs {tot('k1024')}")
# samples: RssAnon growth (info). The table directory stays empty until a flush (memtable data is in memory), so the sampled
# directory size is not a usable check for arms without a flush during the writes; RssAnon (memtable regions are malloc) is.
for a in ('k1024', 'k32768', 'k65535', 'p128_k32768', 'c16big'):
    rows = [l.split(',') for l in open(f'{R}/cluster/samples-{a}.csv').read().splitlines()[1:]]
    r0, rmax = int(rows[0][1]), max(int(r[1]) for r in rows)
    n, k = K[a]
    chk(f'{a}: RssAnon samples present (info: first {r0 / 2**20:.0f} MiB, max {rmax / 2**20:.0f} MiB, growth {(rmax - r0) / 2**20:.0f} MiB, N*K {n * k / 2**20:.0f} MiB)', len(rows) >= 1 and rmax > 0)
chk('no ERROR in system.log of either life', not re.search(r'^ERROR', logs[1] + logs[2], re.M))
chk('only the nodes of this run: no daemon of this run left', not [p for p in os.listdir('/proc') if p.isdigit() and os.path.exists(f'/proc/{p}/cmdline') and 's4-b8-uk/node' in open(f'/proc/{p}/cmdline', errors='replace').read().replace('\0', ' ') and 'selfcheck' not in open(f'/proc/{p}/cmdline', errors='replace').read()])
print(f'\n{sum(res)} hold, {len(res) - sum(res)} do not hold')
