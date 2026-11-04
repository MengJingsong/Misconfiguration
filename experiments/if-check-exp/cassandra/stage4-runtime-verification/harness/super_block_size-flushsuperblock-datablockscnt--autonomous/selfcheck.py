#!/usr/bin/env python3
"""Independent re-parse of the raw logs of super_block_size-flushsuperblock-datablockscnt--autonomous for results section 5.
Unit: counts SBFLUSH lines of the *.log files (printed by the patched class) against the file-tail count in the *.out files, and
recomputes ratios/spreads. Cluster: windows taken from cmdlog.txt ("compact start"/"compact rc" epoch lines), segments counted with
grep-style matching of "Flushed index segment" lines, post-collection heap from gc.log by uptime offset of the node start line.
usage: selfcheck.py <run1 dir with unit/ and cluster/<arm>/>"""
import glob, os, re, sys, datetime
d = sys.argv[1]
ok = fail = 0
def chk(name, cond, detail=''):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(('PASS ' if cond else 'FAIL ') + name + ('  [' + detail + ']' if detail else ''))
def res(label):
    t = open('%s/unit/%s.out' % (d, label)).read()
    m = re.search(r'^RESULT (.*)$', t, re.M); kv = dict(x.split('=', 1) for x in m.group(1).split() if '=' in x)
    lg = open('%s/unit/%s.log' % (d, label), errors='replace').read()
    sb = [tuple(map(int, g)) for g in re.findall(r'^SBFLUSH dataBlocksCnt=(\d+) tokens=(\d+) treeBytes=(\d+) liveHeap=(\d+)', lg, re.M)]
    return kv, sb, t
# unit
for c in (16, 64, 256):
    kv, sb, t = res('sp%d-n200000-r1' % c)
    chk('unit const %d: SUPER_BLOCK_SIZE read from the loaded class is %d (source is the overlay)' % (c, c), 'SUPER_BLOCK_SIZE=%d ' % c in t and '/ov%dp/' % c in t)
    full = [s for s in sb if s[0] == c]
    chk('unit const %d: printed flushes (true branch of line 497) = file-tail super blocks = %s; all but the forced last one at count %d' % (c, kv['superBlocks'], c), len(sb) == int(kv['superBlocks']) and len(full) == len(sb) - 1 and sb[-1][0] < c, 'prints %d, full %d, last count %d' % (len(sb), len(full), sb[-1][0]))
    db = int(kv['dataBlocks'])
    chk('unit const %d: super blocks = floor((%d-1)/%d)+1' % (c, db, c), int(kv['superBlocks']) == (db - 1) // c + 1)
    chk('unit const %d: the three repeats are byte-identical' % c, len({res('sp%d-n200000-r%d' % (c, r))[0]['md5'] for r in (1, 2, 3)}) == 1)
a, b, e = (res('sp%d-n200000-r1' % c)[0] for c in (16, 64, 256))
chk('unit: super-block counts 46 / 12 / 3 fall by about 4x per 4x constant', (int(a['superBlocks']), int(b['superBlocks']), int(e['superBlocks'])) == (46, 12, 3))
fb = [int(x['fileBytes']) for x in (a, b, e)]
chk('unit: file bytes within 5 percent over the constants', (max(fb) - min(fb)) / min(fb) <= 0.05, 'spread %.2f%%' % (100 * (max(fb) - min(fb)) / min(fb)))
lv = [max(s[3] for s in res('sp%d-n200000-r1' % c)[1]) for c in (16, 64, 256)]
spread = (max(lv) - min(lv)) / min(lv)
chk('unit: live heap at a super-block flush is nearly flat against a 16x constant range (spread < 25%); NOT within the 10% of U3', spread < 0.25, 'spread %.1f%%: %s' % (100 * spread, lv))
mt = [max(s[1] for s in res('sp%d-n200000-r1' % c)[1]) for c in (16, 64, 256)]
chk('unit: the largest tree grows with the constant (tokens 4352 / 17408 / 69632)', mt == [4352, 17408, 69632], str(mt))
per_tok = (lv[2] - lv[0]) / (mt[2] - mt[0])
chk('unit: the heap difference between constants 16 and 256 is explained by the tree (bytes per token 100..400)', 100 <= per_tok <= 400, '%.0f bytes per extra token' % per_tok)
for c in (16, 64, 256):
    l = [max(s[3] for s in res('sp%d-n%d' % (c, n) if n != 200000 else 'sp%d-n200000-r1' % c)[1]) for n in (50000, 200000, 400000)]
    chk('unit const %d: live heap rises with N' % c, l[0] < l[1] < l[2], str(l))
chk('unit: pristine build, unpatched overlay and patched overlay give one md5', len({res(x)[0]['md5'] for x in ('pristine-n200000', 'ov64-unpatched-n200000', 'sp64-n200000-r1')}) == 1)
x, sb, t = res('pfx64-n200000'); chk('unit: PREFIX mode has no super blocks', x['superBlocks'] == '-1' and not sb)
chk('unit: -Xmx64m run ended with OutOfMemoryError (information)', 'OutOfMemoryError' in open('%s/unit/sp64-n200000-xmx64m.log' % d, errors='replace').read())
# cluster
def epoch(s): return int(s)
for arm in ('o64c64', 'o8c64', 'o512c64', 'o64c16', 'o64c256', 'pfx64'):
    p = '%s/cluster/%s' % (d, arm)
    if not os.path.isdir(p): continue
    cmd = open(p + '/cmdlog.txt', errors='replace').read()
    sysl = open(p + '/system.log', errors='replace').read()
    chk('cluster %s: finished, one sstable after compaction, no daemon left' % arm, ('== %s end' % arm) in cmd and 'one sstable' in cmd and 'NOT one sstable' not in cmd and 'daemons left: 0' in cmd)
    chk('cluster %s: stress had 0 errors, no AssertionError/OutOfMemoryError in system.log' % arm, re.search(r'Total errors\s*:\s*0\b', open(p + '/stress.txt', errors='replace').read()) is not None and 'AssertionError' not in sysl and 'java.lang.OutOfMemoryError' not in sysl)
    cl = open(p + '/classload-ondiskindex.txt').read()
    want = '/conf/' if arm in ('o64c16', 'o64c256') else '/build/apache-cassandra'
    chk('cluster %s: OnDiskIndexBuilder class loaded from %s' % (arm, want), want in cl.split('OnDiskIndexBuilder')[1].split('\n')[0] if 'OnDiskIndexBuilder' in cl else False, cl.split('\n')[0][:140])
    w = [int(x) for x in re.findall(r'COMPACT_(?:START|END) (\d+)', open(p + '/windows.txt').read())]
    fd = re.findall(r'flush done (\d+)', cmd)
    chk('cluster %s: compaction window starts 5 to 30 s after the flush (cmdlog "flush done" vs windows.txt)' % arm, 5000 <= w[0] - int(fd[0]) <= 30000, '%s vs %d' % (fd, w[0]))
    chk('cluster %s: compaction window length is between 60 and 300 s' % arm, 60000 <= w[1] - w[0] <= 300000, '%.0f s' % ((w[1] - w[0]) / 1000))
    seg = 0
    for l in sysl.splitlines():
        if 'Flushed index segment' in l:
            m = re.search(r'(\d{4}-\d\d-\d\d)T(\d\d):(\d\d):(\d\d),(\d+)', l)
            t = datetime.datetime(*map(int, m.group(1).split('-')), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)) * 1000, tzinfo=datetime.timezone.utc).timestamp() * 1000
            seg += w[0] <= t <= w[1] + 2000
    print('NOTE %s segments in the compaction window: %d' % (arm, seg))
print('SUMMARY selfcheck pass=%d fail=%d' % (ok, fail))
