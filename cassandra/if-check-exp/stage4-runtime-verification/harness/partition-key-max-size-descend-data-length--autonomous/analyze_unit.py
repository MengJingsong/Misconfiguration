#!/usr/bin/env python3
"""Unit-tier analyser: compares the PkStackTest output with the frozen B2f/B2i predictions.
Usage: analyze_unit.py <outdir>   -> prints CHECK lines and writes <outdir>/summary.txt"""
import csv, sys, os

out = sys.argv[1]

def rows(name):
    with open(os.path.join(out, name + '.tsv')) as f:
        return list(csv.DictReader(f, delimiter='\t'))

def expected_len(depth):
    n = 80
    while 5 * depth >= n:
        n *= 2
    return n

lines = []
def check(name, ok, detail):
    lines.append('CHECK %-34s %s  %s' % (name, 'PASS' if ok else 'FAIL', detail))

L = rows('lengths')
EXP = {15: 80, 16: 160, 127: 640, 128: 1280, 1024: 10240, 16384: 163840, 65535: 327680, 65536: 655360}
# 1: exact length of the apply path, all buffer types and repeats
bad = []
for r in L:
    if r['path'] == 'apply':
        l = int(r['L']); got = int(r['dataLen1'])
        want = EXP.get(l, expected_len(l))
        if got != want: bad.append((r['bufferType'], l, r['rep'], got, want))
check('apply data.length = 80*2^k rule', not bad, 'mismatches=%s; rows=%d' % (bad, sum(1 for r in L if r['path'] == 'apply')))
lines.append('  apply lengths (ON_HEAP rep0): ' + ', '.join('L%s=%s' % (r['L'], r['dataLen1']) for r in L if r['path'] == 'apply' and r['bufferType'] == 'ON_HEAP' and r['rep'] == '0'))
# 2: recursive control stays 80
badr = [(r['bufferType'], r['L'], r['status'], r['dataLen1']) for r in L if r['path'] == 'recursive' and r['status'] == 'ok' and r['dataLen1'] != '80']
nsoe = [(r['bufferType'], r['L'], r['status']) for r in L if r['path'] == 'recursive' and r['status'] != 'ok']
check('recursive control keeps data.length 80', not badr, 'violations=%s; recursive non-ok rows=%s' % (badr, nsoe[:6]))
# 3: repeats identical
byk = {}
for r in L:
    byk.setdefault((r['bufferType'], r['L'], r['path']), set()).add((r['dataLen1'], r['onHeap1'], r['offHeap1']))
check('3 repeats identical', all(len(v) == 1 for v in byk.values()), 'distinct-per-key=%s' % max(len(v) for v in byk.values()))
# 4: accounting differential, ON_HEAP
worst = 0.0; accounted_extra = {}
viol = []
for r in L:
    if r['bufferType'] != 'ON_HEAP' or r['path'] != 'apply' or r['rep'] != '0': continue
    rec = [x for x in L if x['bufferType'] == 'ON_HEAP' and x['path'] == 'recursive' and x['L'] == r['L'] and x['rep'] == '0'][0]
    if rec['status'] != 'ok':
        accounted_extra[r['L']] = 'no recursive twin (%s)' % rec['status']; continue
    da = int(r['onHeap1']) - int(r['onHeap0']); dr = int(rec['onHeap1']) - int(rec['onHeap0'])
    stack = 4 * (int(r['dataLen1']) - 80)
    extra = da - dr
    accounted_extra[r['L']] = 'apply delta %d, recursive delta %d, stack growth %d B, accounted extra %d B' % (da, dr, stack, extra)
    if abs(extra) > 0.05 * max(dr, 1) + 64: viol.append(r['L'])
    if int(r['L']) >= 1024 and extra >= 0.5 * stack: viol.append(('refute-threshold', r['L']))
check('sizeOnHeap(apply) == sizeOnHeap(rec) +-5%', not viol, 'violations=%s' % viol)
for k, v in accounted_extra.items(): lines.append('  L=%s: %s' % (k, v))
# 5: deep size grows by the stack
viol = []
for r in L:
    if r['bufferType'] != 'ON_HEAP' or r['path'] != 'apply' or r['rep'] != '0': continue
    rec = [x for x in L if x['bufferType'] == 'ON_HEAP' and x['path'] == 'recursive' and x['L'] == r['L'] and x['rep'] == '0'][0]
    if rec['status'] != 'ok': continue
    gap = int(r['deep1']) - int(rec['deep1'])
    stack = 4 * (int(r['dataLen1']) - 80)
    lines.append('  L=%s: measureDeep(apply)-measureDeep(recursive) = %d B; 4*(len-80) = %d B' % (r['L'], gap, stack))
    if gap < stack: viol.append(r['L'])
check('measureDeep grows by >= 4*(len-80)', not viol, 'violations=%s' % viol)
# 6: threshold knob does not change lengths
ro = rows('lengths-ro1')
d = {(r['bufferType'], r['L'], r['path']): r['dataLen1'] for r in L if r['rep'] == '0'}
badk = [(r['bufferType'], r['L'], r['path'], r['dataLen1'], d.get((r['bufferType'], r['L'], r['path']))) for r in ro if r['status'] == 'ok' and d.get((r['bufferType'], r['L'], r['path'])) != r['dataLen1']]
check('row_overhead_size=1 leaves lengths', not badk, 'diffs=%s rows=%d' % (badk, len(ro)))
# 7: bulk
for name in ('bulk-default', 'bulk-ro1'):
    B = rows(name)
    for sc in ('fresh', 'afterLong65535'):
        b = [r for r in B if r['scenario'] == sc and r['stage'] == 'before'][0]
        a = [r for r in B if r['scenario'] == sc and r['stage'] == 'after'][0]
        lines.append('  %s %s: dataLen %s -> %s, sizeOnHeap %s -> %s, threshold %s -> %s' % (name, sc, b['dataLen'], a['dataLen'], b['sizeOnHeap'], a['sizeOnHeap'], b['allocatedPosThresholdReached'], a['allocatedPosThresholdReached']))
        # fresh trie: the first 16-byte key takes the stack 80 -> 160 (B2i.1) and the 1M puts add nothing; after a 65535-byte key: unchanged
        want_len = '160' if sc == 'fresh' else b['dataLen']
        check('%s %s data.length = %s after 1M puts' % (name, sc, want_len), a['dataLen'] == want_len, '%s->%s' % (b['dataLen'], a['dataLen']))
        check('%s %s sizeOnHeap grows' % (name, sc), int(a['sizeOnHeap']) > int(b['sizeOnHeap']) + 1000000, '%s->%s' % (b['sizeOnHeap'], a['sizeOnHeap']))
        want = (name == 'bulk-ro1')
        check('%s %s threshold after = %s' % (name, sc, want), (a['allocatedPosThresholdReached'] == 'true') == want, a['allocatedPosThresholdReached'])
# 8: key depth
D = rows('depth')
lines.append('  depth: ' + ', '.join('K%s->%s(+%s)' % (r['K'], r['comparableBytes'], r['extra']) for r in D))
extras = {int(r['extra']) for r in D}
check('DecoratedKey depth = K + const', len(extras) == 1, 'extras=%s' % sorted(extras))
dd = {int(r['K']): int(r['comparableBytes']) for r in D}
lines.append('  predicted stack ints from D(K): ' + ', '.join('K%d->%d' % (k, expected_len(v) if k >= 128 else 80) for k, v in dd.items()))
open(os.path.join(out, 'summary.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
