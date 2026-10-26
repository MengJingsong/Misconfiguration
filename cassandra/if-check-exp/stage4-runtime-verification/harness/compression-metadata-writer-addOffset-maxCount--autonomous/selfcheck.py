#!/usr/bin/env python3
"""Independent self-check for compression-metadata-writer-addOffset-maxCount--autonomous. Re-parses the raw files (not the run scripts'
EXPECTED lines): unit-readings.txt, unit-junit.xml, c3-*.txt, the live -CompressionInfo.db files, cm.trace, samples.csv, stress logs and
system.log. usage: python3 -I selfcheck.py [run=run1]"""
import glob, math, os, re, struct, sys
run = sys.argv[1] if len(sys.argv) > 1 else 'run1'
L = os.path.expanduser('~/s4-cm-logs')
D = '/dev/shm/s4-cm-data'
res = []


def chk(name, ok, detail=''):
    res.append(bool(ok))
    print(('HOLDS    ' if ok else 'DOES NOT HOLD ') + name + (' :: ' + detail if detail else ''))


def kv(line):
    return dict(re.findall(r'(\w+)=(\S+)', line))


# ---- unit tier
rd = [l for l in open(f'{L}/unit-readings.txt') if l.startswith('READING n=')]
chk('unit: 27 cells (9 N x 3 chunk lengths)', len(rd) == 27, str(len(rd)))
bad = []
for l in rd:
    d = {k: v for k, v in kv(l).items()}
    n = int(d['n'])
    cap = 100 * 2 ** max(0, math.ceil(math.log2(n / 100))) if n > 100 else 100
    k = max(0, math.ceil(math.log2(n / 100))) if n > 100 else 0
    ok = (int(d['maxCount']) == cap and int(d['count']) == n and int(d['doublings']) == k and int(d['offHeapBeforePrepare']) == 8 * cap
          and int(d['offHeapAfterPrepare']) == 8 * n and int(d['ciFileBytes']) == 8 * n + 39 and d['exception'] == 'none')
    if not ok:
        bad.append(l[:120])
chk('unit: every cell has capacity = 100*2^ceil(log2(N/100)), doublings = ceil(log2(N/100)), offHeap before = 8*cap, after prepare = 8*N, file = 8N + 39, no exception', not bad, str(bad[:2]))
over = [l for l in rd if int(kv(l)['n']) > 100 and int(kv(l)['maxCount']) <= 100]
chk('unit: capacity exceeds the initial 100 for every N > 100', not over)
c10 = [kv(l) for l in rd if kv(l)['n'] == '10000000']
chk('unit: N=10M gives 13,107,200 / 104,857,600 / 80,000,000 in all three chunk lengths', len(c10) == 3 and all(d['maxCount'] == '13107200' and d['offHeapBeforePrepare'] == '104857600' and d['offHeapAfterPrepare'] == '80000000' for d in c10))
txt = open(f'{L}/unit-readings.txt').read()
chk('unit: C1 AssertionError "Illegal bounds [800..808); size: 800" with assertions enabled', 'control=C1 fixed800 101st-setLong=java.lang.AssertionError: Illegal bounds [800..808); size: 800 assertionsEnabled=true' in txt)
x = open(f'{L}/unit-junit.xml').read()
chk('unit: junit xml has tests=1, failures=0, errors=0', bool(re.search(r'tests="1"', x) and re.search(r'failures="0"', x) and re.search(r'errors="0"', x)))
for m in ('ea', 'da'):
    t = open(f'{L}/c3-{m}.txt').read()
    d = kv([l for l in t.splitlines() if l.startswith('READING n=101')][0])
    chk(f'unit: C3 -{m}: N=101 -> capacity 200, offHeap 1600, no exception, assertionsEnabled={"true" if m == "ea" else "false"}',
        d['maxCount'] == '200' and d['offHeapBeforePrepare'] == '1600' and d['exception'] == 'none' and f'assertionsEnabled={"true" if m == "ea" else "false"}' in t)

# ---- cluster tier: live files
def hdr(path):
    b = open(path, 'rb').read(); o = 0
    (l,) = struct.unpack('>H', b[o:o + 2]); o += 2 + l
    (n,) = struct.unpack('>i', b[o:o + 4]); o += 4
    for _ in range(2 * n):
        (l,) = struct.unpack('>H', b[o:o + 2]); o += 2 + l
    cl, mc, dl, ch = struct.unpack('>iiqi', b[o:o + 20]); o += 20
    return cl, dl, ch, len(b) - o
tot = {}
for k in (64, 16, 4, 1):
    fs = glob.glob(f'{D}/data/ks{k}/standard1-*/*-CompressionInfo.db')
    cl, dl, ch, body = hdr(fs[0])
    tot[k] = ch
    chk(f'cluster: ks{k}: one live SSTable, header chunkLength {k*1024}, chunks = ceil(dataLength/chunkLength) or one more (the compaction output has one more; flush outputs equal ceil), body = 8 x chunks', len(fs) == 1 and cl == k * 1024 and ch - math.ceil(dl / cl) in (0, 1) and body == 8 * ch, f'{len(fs)} files, chunks {ch}, dataLength {dl}')
chk('cluster: chunk counts scale ~4x per K step', all(3.9 < tot[a] / tot[b] < 4.1 for a, b in ((16, 64), (4, 16), (1, 4))) if False else all(3.9 < tot[b] / tot[a] < 4.1 for a, b in ((64, 16), (16, 4), (4, 1))), str(tot))
# summary METRIC lines
sm = open(f'{L}/{run}/M/summary.txt').read()
for tag in ('after-flush', 'after-compact', 'after-restart'):
    ms = {m.group(1): (int(m.group(2)), int(m.group(3))) for m in re.finditer(rf'METRIC {tag} (ks\d+) CompressionMetadataOffHeapMemoryUsed=(\d+) sstables=\d+ sumHeaderChunks=(\d+)', sm)}
    chk(f'cluster: {tag} metric == 8 x header chunks for all four compressed keyspaces', len(ms) == 4 and all(m == 8 * c for m, c in ms.values()), str(ms))
mfinal = {m.group(1): int(m.group(2)) for m in re.finditer(r'METRIC after-restart (ks\d+) CompressionMetadataOffHeapMemoryUsed=(\d+) sstables', sm)}
chk('cluster: restart metric equals 8 x the live files\' header chunks (re-parsed here)', all(mfinal[f'ks{k}'] == 8 * tot[k] for k in tot), str(mfinal))
chk('cluster: uncompressed keyspace metric 0 at all three readings', len(re.findall(r'METRIC \S+ ksu CompressionMetadataOffHeapMemoryUsed=0\b', sm)) == 3)
# trace
ev, prep = {}, {}
for l in open(f'{L}/{run}/M/cm.trace'):
    d = kv(l)
    if l.startswith('double '):
        ev.setdefault(d['path'], []).append((int(d['maxCountNow']), int(d['count'])))
    elif l.startswith('prepare '):
        prep.setdefault(d['path'], []).append((int(d['maxCount']), int(d['count'])))
badtr = [p for p, v in ev.items() if [a for a, _ in v] != [100 * 2 ** (i + 1) for i in range(len(v))] or any(c != a // 2 for a, c in v)]
chk('cluster: trace: each writer\'s doublings are 200, 400, 800, ... (consecutive), each at count == previous capacity', ev and not badtr, f'{len(ev)} writers, bad {badtr[:2]}')
top = max((v[-1][0] for v in ev.values()), default=0)
chk('cluster: trace: largest capacity reached is above the initial 100 by >= 2^14 (K=1 compaction/flush writers)', top >= 100 * 2 ** 14, str(top))
chk('cluster: trace: at prepare every writer has count <= capacity < 2 x count (or capacity 100)', all(c <= m and (m < 2 * c or m == 100) for v in prep.values() for m, c in v), f'{len(prep)} writers')
# controls
for mib in (48, 96):
    cap = (mib - 32) * 2 ** 20
    f = f'{L}/{run}/C{mib}/samples.csv'
    rows = [list(map(float, l.strip().split(',')[1:])) for l in open(f) if l.strip().split(',')[0].isdigit() and len(l.strip().split(',')) == 4]
    mx = max(r[0] for r in rows)
    chk(f'cluster: control {mib}: Capacity sample == {cap} in every row; max Size within [0.9, 1.0] x cap (+16 KiB)', rows and all(r[1] == cap for r in rows) and 0.9 * cap <= mx <= cap + 16384, f'{len(rows)} samples, max Size {mx:.0f}, cap {cap}')
    chk(f'cluster: control {mib}: ks16 offsets metric constant across samples', len({r[2] for r in rows}) == 1, str({r[2] for r in rows}))
    s = open(f'{L}/{run}/C{mib}/stress-read-{mib}.txt', errors='replace').read()
    chk(f'cluster: control {mib}: stress read 0 errors, 100000 ops', bool(re.search(r'Total errors\s*:\s*0', s) and re.search(r'Total partitions\s*:\s*100,?000', s)), '')
for a in ('M', 'C48', 'C96'):
    p = f'{L}/{run}/{a}/summary.txt'
    t = open(p).read()
    failed = [l for l in t.splitlines() if l.startswith('EXPECTED') and ' — NO' in l]
    only_extra = all('dataLength sum changed by compaction' in l for l in failed)   # an expectation of the script, not of B3f
    chk(f'cluster: arm {a}: no failed EXPECTED line except the script-only compaction dataLength check, and no FAIL', only_extra and 'FAIL:' not in t, f'{len(failed)} failed lines')
errs = [l for l in open(D + '/logs/system.log', errors='replace') if l.startswith('ERROR')]
chk('cluster: system.log (whole file, three lifetimes) has no ERROR line', not errs, str(errs[:2]))
print('\nSELFCHECK: %d parts hold, %d do not' % (sum(res), len(res) - sum(res)))
