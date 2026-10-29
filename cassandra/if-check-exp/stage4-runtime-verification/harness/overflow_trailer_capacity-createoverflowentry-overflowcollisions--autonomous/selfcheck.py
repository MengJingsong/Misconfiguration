#!/usr/bin/env python3
"""Independent re-parse of the raw logs of overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous for results
section 5. Expectations are recomputed here from the raw READ lines and from the constants (64-byte header, 16-byte entries, 8-byte
slots, 248 tokens per block, 4096-byte blocks), not copied from the harness's EXPECTED lines.
usage: selfcheck.py <run1 dir with unit/unit.out and cluster/<arm>/...>"""
import os, re, sys
d = sys.argv[1]
ok = fail = 0
def chk(name, cond, detail=''):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(('PASS ' if cond else 'FAIL ') + name + ('  [' + detail + ']' if detail else ''))
rd = {}
for l in open(d + '/unit/unit.out'):
    m = re.match(r'READ (.*?) -> (.*)$', l.rstrip())
    if m: rd[m.group(1)] = m.group(2)
def v(r, k):
    m = re.search(r'\b%s=(\d+)' % k, r); return int(m.group(1)) if m else None
def single(tokens, slots): return 64 + 16 * tokens + 8 * slots
def blocks(n):  # numBlocks x 4096 for > 248 tokens: root + ceil(n/248) leaves, the last token alone when n-1 is a multiple of 248
    return None
C = {k: r for k, r in rd.items()}
r = C['C1 4 tokens x 2 large offsets + 20 single (8 slots)']
chk('C1: 24 tokens, 8 slots, bytes = 64 + 24x16 + 8x8', v(r, 'bytes') == single(24, 8) and v(r, 'slots') == 8, r)
chk('C1: serializedSize() before write omits the trailer (448 = 512 - 64)', v(r, 'serializedSizeBeforeWrite') == single(24, 0))
chk('C2: 10 slots throws the overflow assertion', C['C2 5 tokens x 2 large offsets + 19 single (10 slots)'] == 'THROW java.lang.AssertionError: cannot have more than 8 overflow collisions per leaf')
r = C['C3 1 token x 8 offsets']; chk('C3: 8 offsets pass, 8 slots', v(r, 'slots') == 8 and v(r, 'bytes') == single(1, 8), r)
chk('C4: 9 offsets throw', C['C4 1 token x 9 offsets'].startswith('THROW java.lang.AssertionError: cannot have more than 8'))
r = C['C5 248 tokens x 1 small offset']; chk('C5: 248 tokens = one block of 64 + 248x16', v(r, 'numBlocks') == 1 and v(r, 'bytes') == single(248, 0), r)
r = C['C5 249 tokens x 1 small offset']; chk('C5: 249 tokens add blocks: bytes = numBlocks x 4096 and numBlocks > 1', v(r, 'numBlocks') > 1 and v(r, 'bytes') == v(r, 'numBlocks') * 4096, r)
r = C['C6 600 tokens, 8 slots in each of two leaves']
leaves = re.findall(r'leaf(\d)\{tokens=(\d+),overflowEntries=(\d+),slots=(\d+)\}', r)
chk('C6: no exception; 16 slots in all, 8 in each of two leaves, every leaf block 4096 bytes', v(r, 'slots') == 16 and sorted(int(x[3]) for x in leaves)[-2:] == [8, 8] and v(r, 'bytes') == v(r, 'numBlocks') * 4096, r)
r0 = C['C6 control 600 tokens, no overflow']
chk('C6: block bytes with 16 slots equal block bytes with 0 slots', v(r, 'bytes') == v(r0, 'bytes') and v(r, 'numBlocks') == v(r0, 'numBlocks'))
r = C['C7 248 tokens x 2 small offsets (packed)']; chk('C7: packed pairs use 0 slots, size 64 + 248x16', v(r, 'slots') == 0 and v(r, 'bytes') == single(248, 0), r)
est = {int(m.group(1)): int(m.group(2)) for m in re.finditer(r'READ C8 terms=(\d+) estimatedMemoryUse=(\d+)', open(d + '/unit/unit.out').read())}
chk('C8: estimate = (220 + 8) x terms and linear', all(est[n] == 228 * n for n in est) and est[10000] == 10 * est[1000], str(est))
# cluster
def arm(a):
    p = '%s/cluster/%s' % (d, a)
    return p if os.path.isdir(p) else None
def sizes(p):
    t = open(p + '/ls-sstable-dir.txt').read(); out = {}
    for l in t.splitlines()[1:]:
        f = l.split()
        if len(f) >= 9: out[f[8]] = int(f[4])
    return out
for a in ('g8', 'g9'):
    p = arm(a)
    if not p: continue
    sysl = open(p + '/system.log', errors='replace').read(); bm = open(p + '/byteman.txt').read().split('\n'); s = sizes(p)
    chk('%s: collision keys: 0 token mismatches offline, groups seen on the node' % a, 'mismatches=0' in open(p + '/collkeys.txt').read() and 'TOKEN-GROUPS' in open(p + '/token-groups.txt').read(), open(p + '/token-groups.txt').read().strip())
    si = [k for k in s if 'SI_' in k]
    if a == 'g8':
        chk('g8: SI file written, no throw, no assertion in the log', len(si) == 1 and 'BM-OVF-THROW' not in bm and 'cannot have more than 8' not in sysl, str(s))
        ent = [tuple(map(int, re.findall(r'\d+', l))) for l in bm if l.startswith('BM-OVF-ENTRY')]
        chk('g8: Byteman: entries (4 offsets, 0 slots), (4, 4) = 8 slots', ent == [(4, 0), (4, 4)], str(ent))
    else:
        ent = [tuple(map(int, re.findall(r'\d+', l))) for l in bm if l.startswith('BM-OVF-ENTRY')]
        chk('g9: Byteman: three entries 3,3,3 and one throw (9th slot)', ent == [(3, 0), (3, 3), (3, 6)] and bm.count('BM-OVF-THROW') == 1, str(ent))
        chk('g9: ERROR line with the assertion text from thread SASI-Memtable in system.log', re.search(r'^ERROR \[SASI-Memtable:\d+\].*\n(java\.lang\.)?java\.lang\.AssertionError: cannot have more than 8 overflow collisions per leaf', sysl, re.M) is not None or 'AssertionError: cannot have more than 8 overflow collisions per leaf' in sysl)
        chk('g9: the node cannot open the SI file left behind', re.search(r"Can't open index file .*SI_t_v\.db", sysl) is not None, str(si))
        q = open(p + '/index-query.txt').read()
        chk('g9: the index query returns no rows', '(0 rows)' in q or re.search(r'\(\d+ rows\)', q) is None, q.strip().replace('\n', ' | ')[:80])
        cl = [int(l.split(',')[2]) for l in open(p + '/disk.csv').read().splitlines()[1:] if l.count(',') == 3]
        chk('g9: commit log directory does not grow after the failed flush', max(cl) == cl[0] or max(cl) <= 2 * 33554432, 'min %d max %d' % (min(cl), max(cl)))
for a in ('r1e5', 'r1e6'):
    p = arm(a)
    if p:
        s = sizes(p); chk('%s: one SI file and one Data.db' % a, len([k for k in s if 'SI_' in k]) == 1 and len([k for k in s if k.endswith('Data.db')]) == 1, str({k: x for k, x in s.items() if 'SI_' in k or 'Data' in k}))
if arm('r1e5') and arm('r1e6'):
    a, b = sizes(arm('r1e5')), sizes(arm('r1e6'))
    f = lambda s, pat: [x for k, x in s.items() if pat in k][0]
    chk('r1e6 / r1e5: SI and Data.db grow with rows (both ratios 5..15)', 5 <= f(b, 'SI_') / f(a, 'SI_') <= 15 and 5 <= f(b, 'Data.db') / f(a, 'Data.db') <= 15, 'SI %.2f Data %.2f' % (f(b, 'SI_') / f(a, 'SI_'), f(b, 'Data.db') / f(a, 'Data.db')))
for a in ('g8', 'g9', 'r1e5', 'r1e6', 'm1', 'm100', 'g0'):
    p = arm(a)
    if p: chk('%s: finished, no daemon left' % a, ('== %s end' % a) in open(p + '/cmdlog.txt', errors='replace').read() and 'daemons left: 0' in open(p + '/cmdlog.txt', errors='replace').read())
print('SUMMARY selfcheck pass=%d fail=%d' % (ok, fail))
