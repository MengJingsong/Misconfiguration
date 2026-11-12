#!/usr/bin/env python3
"""Self-check: re-read the raw files (not the analyzers' output) and test each statement the conclusion uses."""
import json, re, sys, os, collections, hashlib
W = '/mydata/jingsong-cass-s4/o43'; U = W + '/run1/unit'; C = W + '/run1/cluster'
out = []
def chk(label, ok, note): out.append(f"{'HOLDS' if ok else 'DOES NOT HOLD'} | {label} | {note}")
# freeze
fp = open(W + '/freeze/freeze-pred.txt', 'rb').read()
chk('freeze hash of B2f/B2g/B3f/B3g', hashlib.sha256(fp).hexdigest().startswith('a3812c99'), hashlib.sha256(fp).hexdigest())
# unit: every len line <= P, P values reached JVM
cap = {'4096': 4096, 'default': 8192, '1048576': 1048576, '16777216': 16777216}
for p, P in cap.items():
    t = open(f'{U}/unit-{p}.log').read()
    lens = [int(x) for x in re.findall(r'len=(\d+)', t)] + [int(x) for x in re.findall(r'maxLen=(\d+)', t)]
    big = [int(r) for r, l in re.findall(r'request=(\d+) len=(\d+)', t) if int(r) > P]
    capped = [int(l) for r, l in re.findall(r'request=(\d+) len=(\d+)', t) if int(r) > P]
    chk(f'unit P={p}: {len(lens)} lengths, all <= P', len(lens) == 11 and max(lens) <= P, f'max={max(lens)}')
    chk(f'unit P={p}: requests above P hit the cap (len == P)', all(l == P for l in capped) and len(big) > 0, f'requests>P={big} lens={capped}')
    m = re.search(r'heapDelta=(-?\d+)', t); chk(f'unit P={p}: heapDelta read', m is not None, m.group(0) if m else '')
# unit: positive control grows to 16 MiB
t = open(f'{U}/unit-16777216.log').read()
chk('unit positive control: request 20 MiB -> 16777216 at P=16 MiB', 'request=20971520 len=16777216' in t, '')
# unit: heapDelta = 32 x regions(len) x 1 MiB + const
g1 = open(f'{U}/g1-flags.txt').read(); chk('G1, region 1 MiB in a 1 GiB JVM', 'G1HeapRegionSize                         = 1048576' in g1 and 'UseG1GC                                  = true' in g1, '')
res = {}
for p, L in [('1048576', 1048576), ('16777216', 8388608)]:
    hd = int(re.search(r'heapDelta=(-?\d+)', open(f'{U}/unit-{p}.log').read()).group(1))
    reg = -(-(L + 16) // (1 << 20)); res[p] = hd - 32 * reg * (1 << 20)
chk('unit heapDelta - 32*regions*1MiB is the same constant at both high P', res['1048576'] == res['16777216'] and 0 <= res['1048576'] < (1 << 20), str(res))
# cluster: from raw files
for lab, Pexp in [('default', None), ('p1m', '1048576'), ('p16m', '16777216'), ('control', '16777216')]:
    s = open(f'{C}/{lab}/session.log').read()
    if Pexp: chk(f'cluster {lab}: jinfo shows P', f'cassandra.data_output_stream_plus_temp_buffer_size={Pexp}' in s, '')
    else: chk(f'cluster {lab}: P unset', 'P unset (default 8192)' in s, '')
    chk(f'cluster {lab}: read "ok 64"', 'ok 64' in open(f'{C}/{lab}/read.log').read(), '')
    rb = re.search(r'(\d+) hits, (\d+) requests', open(f'{C}/{lab}/info-before.txt').read()).groups()
    ra = re.search(r'(\d+) hits, (\d+) requests', open(f'{C}/{lab}/info-after.txt').read()).groups()
    chk(f'cluster {lab}: 64 misses on the read pass', (int(ra[1]) - int(ra[0])) - (int(rb[1]) - int(rb[0])) == 64, f'before={rb} after={ra}')
    chk(f'cluster {lab}: SSTable count 0 before and after reads', 'SSTable count: 0' in open(f'{C}/{lab}/tablestats-before.txt').read() and 'SSTable count: 0' in open(f'{C}/{lab}/tablestats-after.txt').read(), '')
    alloc = 'heap_buffers' if lab == 'control' else 'offheap_buffers'
    chk(f'cluster {lab}: memtable_allocation_type {alloc}', f'memtable_allocation_type: {alloc}' in s, '')
    d = json.load(open(f'{C}/jfr-{lab}.json'))
    ev = d['recording']['events']
    tb = [e for e in ev if any(f['method']['name'] == 'retrieveTemporaryBuffer' for f in (e['values'].get('stackTrace') or {}).get('frames', []))]
    hc = [e for e in ev if (e['values'].get('allocationSize') or 0) >= 4 << 20 and any(f['method']['type']['name'].endswith('HeapCloner') for f in (e['values'].get('stackTrace') or {}).get('frames', []))]
    chk(f'cluster {lab}: JFR has allocation events, none with retrieveTemporaryBuffer in the stack', len(ev) > 100 and len(tb) == 0, f'events={len(ev)} tempbuf={len(tb)}')
    chk(f'cluster {lab}: 4 MiB allocations by HeapCloner (memtable clone to heap)' + (' expected only for offheap' if lab != 'control' else ' (heap_buffers: expected none)'),
        (len(hc) > 0) == (lab != 'control'), f'HeapCloner >=4MiB events={len(hc)}')
    def hb(f): return int(re.search(r'^\s*\d+:\s+\d+\s+(\d+)\s+\[B \(java\.base', open(f'{C}/{lab}/{f}').read(), re.M).group(1))
    dH = hb('hist1-full.txt') - hb('hist0-full.txt')
    chk(f'cluster {lab}: |dH| < 16 MiB', abs(dH) < 16 << 20, f'dH={dH}')
print('\n'.join(out)); print(f"SUMMARY holds={sum(1 for o in out if o.startswith('HOLDS'))} does_not_hold={sum(1 for o in out if o.startswith('DOES'))}")
