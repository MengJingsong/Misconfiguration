#!/usr/bin/env python3
"""Independent re-parse of the run-1 raw files of max_shard_split-getnumshards-count--autonomous.
usage: selfcheck.py <run1 dir>   (contains unit/unit-1.out unit-2.out ant-*.log and cluster/run1/{snaps.jsonl,readings.txt,shardlines-*.txt,compacting-*.txt,samples.csv})
Recomputes every unit cell from the formula in Controller.getNumShards (written here from the source, not from the run), and re-tests the cluster readings."""
import json, math, os, re, sys
R = sys.argv[1]; fails = 0
def chk(ok, msg):
    global fails; fails += (not ok); print(('PASS ' if ok else 'FAIL ') + msg)
def i32(x): x &= 0xffffffff; return x - (1 << 32) if x >= (1 << 31) else x
def hob(x): return 0 if x == 0 else 1 << (x.bit_length() - 1)
def model(g, target, base, d, minsz=0):
    if minsz > 0:
        c = d / minsz
        if not (c >= base):   # also NaN
            cnt = 0 if math.isnan(c) else int(c)
            return min(hob(i32(cnt | 1)), base & -base)
    if g == 1: return base
    if g == 0:
        c = d / (target * math.sqrt(0.5) * base)
        if c > 2 ** 20: c = 2.0 ** 20
        cnt = 0 if math.isnan(c) else (2 ** 31 - 1 if c >= 2 ** 31 else int(c))
        return i32(base * hob(cnt | 1))
    c = d / (target * base)
    lg = (math.log(c) if c > 0 else -math.inf) if not math.isnan(c) else math.nan
    pw = lg * (1 / math.log(2)) * (1 - g) + 0.5
    if math.isnan(pw): return base
    if pw >= 20: return i32(base << 20)
    if pw >= 0: return i32(base << int(pw))
    return base
# ---- unit
cells = {}
for rep in (1, 2):
    p = os.path.join(R, 'unit', 'unit-%d.out' % rep)
    for l in open(p):
        m = re.match(r'STAGE4 shards growth=(\S+) target=(\S+) base=(\d+) d=(\S+) dval=(\S+) K=(\S+) shards=(-?\d+) repeat=(-?\d+) cap=(\d+)', l)
        if m:
            g, t, b, dn, dv, K, s, rp, cap = m.groups()
            cells[(rep, g, t, int(b), dn)] = (float(dv), float(K), int(s), int(rp), int(cap))
chk(len(cells) == 2 * 330, 'unit: 330 cells in each of 2 probe JVMs (%d read)' % len(cells))
bad = 0; flip = 0
for (rep, g, t, b, dn), (dv, K, s, rp, cap) in cells.items():
    tb = 1 << 20 if t == '1MiB' else 1 << 30
    exp = model(float(g), tb, b, dv)
    # boundary cells where float rounding of log could differ by one power of two are listed, not hidden
    if exp != s: bad += 1; print('   mismatch', rep, g, t, b, dn, 'observed', s, 'model', exp)
    if s != rp: flip += 1
chk(bad == 0, 'unit: all %d observed shard counts equal the independent model of getNumShards (%d mismatches)' % (len(cells), bad))
chk(flip == 0, 'unit: every repeated call returns the same value (no state)')
chk(all(cells[(1,)+k[1:]][2] == cells[(2,)+k[1:]][2] for k in cells if k[0] == 1), 'unit: the two JVMs agree on every cell')
# predictions of B2f, restated here
for rep in (1,):
    for t in ('1MiB', '1GiB'):
        for b in (1, 4, 2047, 2048, 4096):
            for dn in ('NaN', '0'):
                chk(cells[(rep, '0', t, b, dn)][2] == b, 'growth 0 %s base %d d=%s -> baseShardCount' % (t, b, dn))
            for b2 in (b,):
                chk(all(cells[(rep, '1', t, b, dn)][2] == b for dn in ('K/4', '2K', 'MAX_VALUE', '+Inf', 'NaN', '0')), 'growth 1 %s base %d -> baseShardCount for every density' % (t, b))
for b, want in ((1, 1 << 20), (4, 4 << 20), (2047, 2047 << 20), (2048, -2147483648), (4096, 0)):
    ds = ('1.01K', '2K', '2^10K', '2^40K', 'MAX_VALUE', '+Inf')
    vals = [cells[(1, '0', '1MiB', b, dn)][2] for dn in ds]
    chk(all(v == want for v in vals), 'growth 0 target 1MiB base %d: d >= 1.01K gives %d (observed %s)' % (b, want, sorted(set(vals))))
    v2 = [cells[(1, '0.333', '1MiB', b, dn)][2] for dn in ('2^40K', 'MAX_VALUE', '+Inf')]
    print('   info growth 0.333 target 1MiB base %d huge density ->' % b, sorted(set(v2)))
chk(all(cells[(1, '0', '1MiB', 1, dn)][2] < (1 << 20) for dn in ('K/4', 'K/2', '0.99K')), 'growth 0 base 1: d <= 0.99K is below 2^20')
# control: min_sstable_size
ctl = {}
for l in open(os.path.join(R, 'unit', 'unit-1.out')):
    m = re.match(r'STAGE4 control-min min=(\S+) base=4 target=1GiB growth=0 d=(\S+) shards=(\d+)', l)
    if m: ctl.setdefault(m.group(1), []).append(int(m.group(3)))
print('   control-min', ctl)
chk(ctl.get('0MiB') == [4] * 6 and ctl.get('100MiB') != ctl.get('0MiB') and min(ctl.get('100MiB', [4])) < 4, 'unit positive control: min_sstable_size 100MiB moves the shard count below base (0MiB: always base)')
# tracker
tr = {}
for rep in (1, 2):
    for l in open(os.path.join(R, 'unit', 'unit-%d.out' % rep)):
        m = re.match(r'STAGE4 tracker rep=(\d) shards=(\d+) count=\d+ trackers=20000 heapDelta=(-?\d+) perTracker=(\S+)', l)
        if m: tr.setdefault((rep, int(m.group(1))), {})[int(m.group(2))] = float(m.group(4))
allv = [v for (rep, r), d in tr.items() for s, v in d.items() if r >= 1]
chk(len(allv) == 2 * 2 * 3 and max(allv) / min(allv) < 1.05, 'unit: per-tracker retained heap is %.1f..%.1f B at 4 / 1024 / 2^20 shards (reps 1-2, both JVMs; constant within 5%%)' % (min(allv), max(allv)))
print('   info rep 0 (cold) per-tracker:', {k: v for k, v in tr.items() if k[1] == 0})
log = open(os.path.join(R, 'chain.log')).read()
chk('ControllerTest-_jdk11 Tests run: 1, Failures: 0, Errors: 0' in log, 'upstream ControllerTest#testGetNumShards passed (instrument known-answer check)')
# ---- cluster
C = os.path.join(R, 'cluster', 'run1')
if os.path.exists(C + '/snaps.jsonl'):
    snaps = {}
    for l in open(C + '/snaps.jsonl'): d = json.loads(l); snaps[d['snap']] = d
    def shard_vals(tag):
        v = []
        p = C + '/shardlines-%s.txt' % tag
        if os.path.exists(p):
            for l in open(p):
                m = re.search(r'Shard count (-?\d+) for density', l)
                if m: v.append(int(m.group(1)))
        return v
    for arm in ('A-dense', 'A-control', 'B-dense', 'B-control'):
        if arm + '-postcompact' not in snaps: print('   (no', arm, ')'); continue
        a, b = snaps[arm + '-postflush'], snaps[arm + '-postcompact']
        print('   info %s: compact shard values %s flush-phase %s | sstables %s -> %s | live %s -> %s | heap post-GC kB %s -> %s | du %s -> %s | RssAnon %s' % (
            arm, sorted(set(shard_vals(arm + '-compact'))), sorted(set(shard_vals(arm + '-flushphase'))), a['SSTable count'], b['SSTable count'], a['Space used (live)'], b['Space used (live)'],
            a['heap_post_gc_kB'], b['heap_post_gc_kB'], a['du_bytes'], b['du_bytes'], b['RssAnon_kB']))
    ad = shard_vals('A-dense-compact'); ac = shard_vals('A-control-compact')
    chk(bool(ad) and max(ad) == 1 << 20, 'cluster A-dense: the compaction logged shard count 1048576 (the clamp): %s' % sorted(set(ad)))
    chk(bool(ac) and max(ac) <= 512, 'cluster A-control: logged shard count <= 512: %s' % sorted(set(ac)))
    if 'B-dense-postcompact' in snaps:
        bd = shard_vals('B-dense-compact'); bc = shard_vals('B-control-compact')
        chk(bool(bd) and max(bd) < (1 << 20) and bool(bc) and max(bc) < (1 << 20), 'cluster B: clamp not reached in either arm (dense %s, control %s)' % (sorted(set(bd)), sorted(set(bc))))
    live = lambda a: int(snaps[a + '-postcompact']['Space used (live)'])
    if 'A-control-postcompact' in snaps:
        chk(abs(live('A-dense') - live('A-control')) / live('A-control') < 0.05, 'cluster A: live bytes after compaction equal within 5%% across arms (%d vs %d)' % (live('A-dense'), live('A-control')))
        h1, h2 = snaps['A-dense-postcompact']['heap_post_gc_kB'], snaps['A-control-postcompact']['heap_post_gc_kB']
        chk(max(h1, h2) / min(h1, h2) < 2, 'cluster A: post-GC heap after compaction within 2x across arms (%d vs %d kB; shard counts differ by %dx)' % (h1, h2, (1 << 20) // max(ac)))
print('SELFCHECK fails=%d' % fails)
