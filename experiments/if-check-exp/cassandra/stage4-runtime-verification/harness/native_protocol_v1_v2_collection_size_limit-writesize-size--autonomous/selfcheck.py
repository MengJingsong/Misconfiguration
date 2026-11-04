#!/usr/bin/env python3
"""Independent re-parse of the raw logs of native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous run 1.
usage: selfcheck.py <logs dir, e.g. ~/s4-b34/logs/collection_size_limit/run1>. unit/test.out; cluster/{default,control}/{stdout.txt,system.log,readings.txt,datalist.txt}."""
import re, sys, collections, statistics
D = sys.argv[1]; res = []
def chk(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + detail) if detail else ''))
def kv(line):
    d = dict(re.findall(r'(\w+)=(\S+)', line))
    if 'ver' in d and d['ver'][:1].isdigit() and '/' in d['ver'] and not line.startswith('STAGE4'): d['ver'] = d['ver'].split('/')[1].upper()   # Byteman prints ProtocolVersion as 3/v3
    return d
cells = [kv(l) for l in open(D + '/unit/test.out') if l.startswith('STAGE4 cell')]
chk('unit: 54 cells', len(cells) == 54, str(len(cells)))
g = collections.defaultdict(list)
for c in cells: g[(c['ver'].split('/')[1], int(c['N']), int(c['S']))].append(c)
chk('unit: 3 reps per cell', all(len(v) == 3 for v in g.values()))
def exp_len(v, n, s): return 2 + n * (2 + s) if v == 'v2' else 4 + n * (4 + s)
ok = True; d = ''
for (v, n, s), cs in g.items():
    for c in cs:
        if v == 'v2' and n > 65535:
            good = c['outcome'] == 'IllegalArgumentException' and 'supports_up_to_65535_elements_in_any_collection' in c['msg'] and ('contains_%d_elements' % n) in c['msg']
        else:
            good = c['outcome'] == 'ok' and int(c['len']) == exp_len(v, n, s) and int(c['count']) == n
        if not good: ok = False; d = str((v, n, s, c))
chk('unit: V2 throws only above 65535 (with the count message); every other cell succeeds with the exact length and count field', ok, d)
med = {k: statistics.median(int(c['alloc']) for c in cs) for k, cs in g.items()}
rat = {}
for (v, n, s) in g:
    if v == 'v2' and n > 65535: rat[(n, s)] = (med[(v, n, s)] / med[('v3', n, s)], med[(v, n, s)], exp_len('v2', n, s))
chk('unit: failing V2 call allocated >= 0.8 x the V3 call at the same N,S, and >= its own V2 result size', all(r >= 0.8 and a >= e for r, a, e in rat.values()), str(rat))
r34 = {(n, s): med[('v3', n, s)] / med[('v4', n, s)] for (v, n, s) in g if v == 'v3'}
print('INFO V3/V4 median allocation ratio per cell:', {k: round(v, 3) for k, v in r34.items()}, ' (the first measured cell, N=65535 S=1, carries warm-up noise: reps %s)' % [(c['ver'], c['alloc']) for c in g[('v3', 65535, 1)] + g[('v4', 65535, 1)]])
chk('unit: V3 and V4 allocate the same (+-5%) in every cell except the first measured one (warm-up)', all(abs(v - 1) < 0.05 for k, v in r34.items() if k != (65535, 1)))
diff = med[('v3', 200000, 100)] - med[('v3', 200000, 1)]
chk('unit control: V3 N=200000, 100 B payload allocates >= 0.9*99*N more than 1 B', diff >= 0.9 * 99 * 200000, str(diff))
chk('unit: alloc rises with N for V3 at S=1 (65535 < 200000)', med[('v3', 65535, 1)] < med[('v3', 200000, 1)])
# ---------------- cluster
def load(m):
    C = D + '/cluster/' + m
    return open(C + '/stdout.txt', errors='replace').read(), open(C + '/system.log', errors='replace').read(), open(C + '/readings.txt').read()
so, sl, rd = load('default')
chk('cluster: V2 probe refused (client: connected=no) and the server log names the protocol version, not 65535', 'V2PROBE connected=no' in rd and 'Invalid or unsupported protocol version (2); supported versions are (3/v3, 4/v4, 5/v5, 6/v6-beta)' in so and '65535' not in re.search(r'V2PROBE.*', rd).group(0), re.search(r'V2PROBE.*', rd).group(0)[:160])
w = re.findall(r'W_INSERT N=(\d+) (\S+)', rd)
chk('cluster: W inserts of 1000, 65536, 500000 all accepted (v4), no error mentioning 65535', [x[1] for x in w] == ['accepted'] * 3 and '65535' not in ' '.join(re.findall(r'W_INSERT.*', rd)), str(w))
wu = {int(m.group(1)): kv(m.group(0)) for m in re.finditer(r'W_USAGE N=(\d+) .*', rd)}
chk('cluster: read-back elements == N for the 3 sizes; Byteman pack_calls during W == 0', all(int(wu[n]['readback_elements']) == n and int(wu[n]['pack_calls']) == 0 for n in wu), str(wu))
for key in ('memtable_data_bytes', 'sstable_data_bytes'):
    bp = {n: int(wu[n][key]) / n for n in (1000, 65536, 500000)}
    chk('cluster: %s per element at N=65536 and 500000 within 25%% (no step at 65535)' % key, abs(bp[500000] / bp[65536] - 1) <= 0.25, str(bp))
    chk('cluster: %s grows with N' % key, int(wu[1000][key]) < int(wu[65536][key]) < int(wu[500000][key]))
packs = [kv(l) for l in so.splitlines() if l.startswith('CS_PACK ')]
ws = [kv(l) for l in so.splitlines() if l.startswith('CS_WRITESIZE ')]
rets = [kv(l) for l in so.splitlines() if l.startswith('CS_PACK_RET ')]
chk('cluster: UDF path reached CodecUtils: 6 pack calls (3 N x v4,v3), with ver V4/V3 only and elements in {1000,65536,500000}', len(packs) == 6 and sorted(p['ver'] for p in packs) == ['V3'] * 3 + ['V4'] * 3 and sorted(int(p['elements']) for p in packs) == [1000, 1000, 65536, 65536, 500000, 500000], str(packs))
chk('cluster: writeSize saw size N (incl. 65536 and 500000) under V3/V4, never V1/V2', len(ws) == 6 and all(x['ver'] in ('V3', 'V4') for x in ws) and sorted(int(x['size']) for x in ws) == [1000, 1000, 65536, 65536, 500000, 500000])
chk('cluster: pack result length == 4 + 8N (list<int>)', sorted(int(r['len']) for r in rets) == sorted(4 + 8 * n for n in (1000, 65536, 500000) for _ in range(2)))
uq = re.findall(r'U_QUERY proto=(v\d) N=(\d+) (ok elements=\d+|error.*?) heapmax', rd)
chk('cluster: all 6 UDF queries returned N elements, none errored', len(uq) == 6 and all(x[2] == 'ok elements=%s' % x[1] for x in uq), str(uq))
chk('cluster: no 65535 text in the node log', '65535 elements' not in sl and '65535 elements' not in so)
# control
so2, sl2, rd2 = load('control')
w2 = re.findall(r'W_INSERT N=(\d+) (accepted|rejected.*)', rd2)
print('INFO control W_INSERT:', [(a, b[:160]) for a, b in w2])
chk('cluster control (collection_size_fail_threshold 200KiB): N=1000 accepted; 65536 and 500000 rejected', [b.split()[0] for a, b in w2] == ['accepted', 'rejected', 'rejected'])
chk('cluster control: the rejection is a guardrail message (mentions the threshold/collection), not the 65535 text', all(('ollection' in b or 'threshold' in b) and '65535' not in b for a, b in w2 if b.startswith('rejected')))
chk('cluster control: yaml line present in the control node', 'collection_size_fail_threshold=200KiB' in so2.replace(' ', '') or 'collection_size_fail_threshold=200' in so2)
print('RESULT %d PASS %d FAIL' % (sum(res), len(res) - sum(res)))
