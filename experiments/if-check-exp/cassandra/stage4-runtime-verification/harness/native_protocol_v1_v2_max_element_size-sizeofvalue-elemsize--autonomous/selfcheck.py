#!/usr/bin/env python3
"""Independent re-parse of the raw logs of native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous run 1.
usage: selfcheck.py <logs dir, e.g. ~/s4-b34/logs/max_element_size/run1>."""
import re, sys, collections, statistics
D = sys.argv[1]; res = []
def chk(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + detail) if detail else ''))
def kv(line):
    d = dict(re.findall(r'(\w+)=(\S+)', line))
    if 'ver' in d and d['ver'][:1].isdigit() and '/' in d['ver'] and not line.startswith('STAGE4'): d['ver'] = d['ver'].split('/')[1].upper()   # Byteman prints ProtocolVersion as 3/v3
    return d
raw = open(D + '/unit/test.out').read().splitlines()
cells = [kv(l) for l in raw if l.startswith('STAGE4 cell')]
chk('unit: 81 cells', len(cells) == 81, str(len(cells)))
g = collections.defaultdict(list)
for c in cells: g[(c['tag'], c['ver'].split('/')[1], int(c['N']), int(c['S']))].append(c)
chk('unit: 3 reps per cell', all(len(v) == 3 for v in g.values()))
def exp_len(v, n, s): return 2 + n * (2 + s) if v == 'v2' else 4 + n * (4 + s)
ok = True; d = ''
for (t, v, n, s), cs in g.items():
    for c in cs:
        if v == 'v2' and s > 65535:
            good = c['outcome'] == 'IllegalArgumentException' and 'supports_only_elements_with_size_up_to_65535_bytes' in c['msg'] and ('element_size_is_%d_bytes' % s) in c['msg']
        else:
            good = c['outcome'] == 'ok' and int(c['len']) == exp_len(v, n, s) and int(c['len']) == int(c['expectedLen'])
        if not good: ok = False; d = str(c)
chk('unit: V2 throws exactly when S > 65535 (with the size message); every other cell succeeds with the exact length; V3/V4 succeed at 8 MiB', ok, d)
med = {k: statistics.median(int(c['alloc']) for c in cs) for k, cs in g.items()}
chk('unit: failing V2 calls (S=65536, 8 MiB) allocate < 16 KB (result buffer never allocated)', all(med[k] < 16384 for k in med if k[1] == 'v2' and k[3] > 65535), str({k: v for k, v in med.items() if k[1] == 'v2' and k[3] > 65535}))
chk('unit: V3 at S=65536 and 8 MiB allocates at least the result size', med[('size', 'v3', 1, 65536)] >= 65544 and med[('size', 'v3', 1, 8388608)] >= 8388616)
ok2 = True
for v in ('v2', 'v3', 'v4'):
    per = [med[('ctl', v, n, 65535)] / n for n in (1, 10, 100, 1000)]
    if max(per) / min(per) > 1.10: ok2 = False
chk('unit control: allocated bytes per element within 10% across N = 1, 10, 100, 1000 (V2, V3, V4) - proportional to payload', ok2)
nl = [l for l in raw if l.startswith('STAGE4 null')]
chk('unit: null element -> NPE on V2, ok len=8 on V3', any('ver=2/v2 outcome=NullPointerException' in l for l in nl) and any('ver=3/v3 outcome=ok len=8' in l for l in nl), str(nl))
def load(m):
    C = D + '/cluster/' + m
    return open(C + '/stdout.txt', errors='replace').read(), open(C + '/system.log', errors='replace').read(), open(C + '/readings.txt').read()
so, sl, rd = load('default')
chk('cluster: V2 probe refused (client: connected=no) and the server log names the protocol version, not an element size', 'V2PROBE connected=no' in rd and 'Invalid or unsupported protocol version (2); supported versions are (3/v3, 4/v4, 5/v5, 6/v6-beta)' in so and 'element' not in re.search(r'V2PROBE.*', rd).group(0), re.search(r'V2PROBE.*', rd).group(0)[:160])
wi = re.findall(r'W_INSERT S=(\d+) rows_ok=(\d+) of 100 first_error=(.*)', rd)
chk('cluster: W inserts of 65535, 65536 and 1 MiB elements all accepted on v4 (100 rows each)', [(a, b) for a, b, c in wi] == [('65535', '100'), ('65536', '100'), ('1048576', '100')], str(wi))
wu = {int(m.group(1)): kv(m.group(0)) for m in re.finditer(r'W_USAGE S=(\d+) .*', rd)}
chk('cluster: read-back 1 element, Byteman pack_calls during W == 0', all(int(wu[s]['readback_elements']) == 1 and int(wu[s]['pack_calls']) == 0 for s in wu), str(wu))
# A MEMTABLE_LIMIT flush of tw_1048576 happened during the insert (system.log), so the memtable leg is only valid for 65535 and 65536; the disk leg (sum of all Data.db) is valid for all three.
ml = re.findall(r'Enqueuing flush of ks\.(tw_\d+), Reason: MEMTABLE_LIMIT', sl)
print('INFO MEMTABLE_LIMIT flushes during W:', ml)
chk('cluster: only tw_1048576 hit a MEMTABLE_LIMIT flush during its inserts (memtable leg invalid for it, valid for the two smaller)', ml and set(ml) == {'tw_1048576'}, str(ml))
bm = {s: int(wu[s]['memtable_data_bytes']) / (100 * s) for s in (65535, 65536)}
chk('cluster: memtable bytes per payload byte at S=65535 and 65536 within 5% (no step at 65535)', abs(bm[65536] / bm[65535] - 1) <= 0.05, str(bm))
bd = {s: int(wu[s]['sstable_data_bytes']) / (100 * s) for s in wu}
chk('cluster: SSTable bytes per payload byte at S=65535, 65536 and 1 MiB within 25% of each other (no step at 65535)', max(bd.values()) / min(bd.values()) <= 1.25, str(bd))
chk('cluster: SSTable bytes grow with S', int(wu[65535]['sstable_data_bytes']) < int(wu[65536]['sstable_data_bytes']) < int(wu[1048576]['sstable_data_bytes']))
sz = [kv(l) for l in so.splitlines() if l.startswith('ES_SIZEOF ')]
chk('cluster: sizeOfValue saw remaining 65535, 65536, 1048576 under V3/V4 (UDF path), never V1/V2', sorted((x['ver'], int(x['remaining'])) for x in sz) == sorted((v, s) for v in ('V3', 'V4') for s in (65535, 65536, 1048576)), str([(x['ver'], x['remaining']) for x in sz]))
uq = re.findall(r'U_QUERY proto=(v\d) S=(\d+) (ok elements=1 first_len=\d+|error.*?) heapmax', rd)
chk('cluster: all 6 UDF queries returned the element (first_len == S), none errored', len(uq) == 6 and all(x[2] == 'ok elements=1 first_len=%s' % x[1] for x in uq), str(uq))
chk('cluster: no "supports only elements" text in the node log', 'supports only elements' not in sl and 'supports only elements' not in so)
so2, sl2, rd2 = load('control')
w2 = re.findall(r'W_INSERT S=(\d+) rows_ok=(\d+) of 100 first_error=(.*)', rd2)
print('INFO control W_INSERT:', [(a, b, c[:160]) for a, b, c in w2])
chk('cluster control (column_value_size_fail_threshold 512KiB): S=65535, 65536 accepted (100 rows); 1 MiB rejected (0 rows)', [(a, b) for a, b, c in w2] == [('65535', '100'), ('65536', '100'), ('1048576', '0')])
chk('cluster control: rejection is a guardrail message, not the element-size text', 'supports only elements' not in w2[2][2] and ('uardrail' in w2[2][2] or 'hreshold' in w2[2][2] or 'olumn' in w2[2][2]), w2[2][2][:200])
print('RESULT %d PASS %d FAIL' % (sum(res), len(res) - sum(res)))
