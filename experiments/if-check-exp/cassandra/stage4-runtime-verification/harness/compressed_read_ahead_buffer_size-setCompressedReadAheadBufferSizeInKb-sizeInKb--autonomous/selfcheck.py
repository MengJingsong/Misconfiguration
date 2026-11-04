#!/usr/bin/env python3
"""Independent self-check (results §5) of
compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous, run 1.
Written before the run-1 readings. Re-derives every B2f and B3f clause (as amended 2026-10-25) from the raw files; never reads
summary.txt. Unit: unit-<run>/stage4.out (the test's own STAGE4 lines) and ant-<rep>.log. Cluster: per start <start>/system.log and
<start>/readahead.trace; per arm <arm>/poll.csv and <arm>/tablestats-{before,after}.txt; commands.log only for the setter client
output (SET lines), the compaction exit code and client window (COMPACT lines), which no other file holds.
usage: selfcheck.py <logs dir> [unit run name] [cluster run name]
"""
import os, re, statistics, sys

base = sys.argv[1]
urun = sys.argv[2] if len(sys.argv) > 2 else 'run1'
crun = sys.argv[3] if len(sys.argv) > 3 else 'run1'
MiB = 1048576
KB40 = 40 * 1024
res = []


def check(name, ok, note=''):
    res.append(ok)
    print('%s %s %s' % ('HOLDS' if ok else 'FAILS', name, note))


def info(name, note):
    print('INFO %s %s' % (name, note))


def kv(line):
    return dict(re.findall(r'(\w+)=(\{[^}]*\}|\S+)', line))


# ---------------- unit ----------------
U = os.path.join(base, 'unit-' + urun)
lines = open(os.path.join(U, 'stage4.out')).read().splitlines() if os.path.exists(os.path.join(U, 'stage4.out')) else []
reps = sorted({kv(l).get('label') for l in lines})
check('unit.reps', reps == ['rep1', 'rep2', 'rep3'], str(reps))
for rep in reps:
    L = [l for l in lines if ' label=%s ' % rep in l + ' ']
    ant = open(os.path.join(U, 'ant-%s.log' % rep)).read()
    m = re.search(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+)', ant)
    check('unit.%s.ant' % rep, bool(m) and m.groups() == ('1', '0', '0') and 'BUILD SUCCESSFUL' in ant, m.group(0) if m else 'no Tests run line')
    check('unit.%s.done' % rep, any(l.startswith('STAGE4 done') for l in L))
    rb = [l for l in L if l.startswith('STAGE4 readback')]
    r = kv(rb[0]) if rb else {}
    check('unit.%s.readback' % rep, r.get('sstables') == '1' and r.get('chunkLength') == '16384' and r.get('factory') == 'CompressedChunkReader$Standard'
          and r.get('captured') == '262144' and r.get('fileCacheEnabled') == 'false' and r.get('diskAccessMode') == 'standard' and r.get('getterKiB') == '256',
          rb[0][len('STAGE4 readback '):] if rb else 'missing')
    sets = {(kv(l)['tag'], kv(l)['v']): l for l in L if l.startswith('STAGE4 set')}
    for v in ('0', '128', '255'):
        l = sets.get(('reject', v), '')
        check('unit.%s.reject.%s' % (rep, v), ' REJECTED IllegalArgumentException compressed_read_ahead_buffer_size_in_kb must be at least 256KiB getterKiB=256' in l, l[l.find('v='):])
    l = sets.get(('reject', '2097152'), '')
    check('unit.%s.reject.2097152' % rep, ' REJECTED ConfigurationException compressed_read_ahead_buffer_size must be positive value <= 2147483646B, but was 2147483648B getterKiB=256' in l, l[l.find('v='):])
    l = sets.get(('max', '2097151'), '')
    check('unit.%s.max.2097151' % rep, l.endswith('ACCEPTED getterKiB=2097151'), l[l.find('v='):])
    readers = {kv(l)['tag']: kv(l) for l in L if l.startswith('STAGE4 reader')}
    cycles = {(kv(l)['tag'], kv(l)['T']): kv(l) for l in L if l.startswith('STAGE4 cycle')}
    for v in (256, 1024, 4096, 16384):
        tag = 'v%d' % v
        l = sets.get((tag, str(v)), '')
        check('unit.%s.%s.set' % (rep, tag), l.endswith('ACCEPTED getterKiB=%d' % v), l[l.find('v='):])
        rd = readers.get(tag, {})
        check('unit.%s.%s.captured' % (rep, tag), rd.get('factory') == 'CompressedChunkReader$Standard' and rd.get('captured') == str(v * 1024), str(rd.get('captured')))
        for T in (1, 8):
            c = cycles.get((tag, str(T)), {})
            if not c:
                check('unit.%s.%s.T%d' % (rep, tag, T), False, 'missing'); continue
            check('unit.%s.%s.T%d.per_buffer' % (rep, tag, T), c['workers'] == '{entries=1 own=%d:direct=%d}' % (v * 1024, T), c['workers'])
            E = T * v * 1024
            oc, cc = int(c['openDeltaC']), int(c['closedDeltaC'])
            check('unit.%s.%s.T%d.openDeltaC' % (rep, tag, T), abs(oc - E) <= T * KB40, 'openDeltaC=%d E=%d diff=%d band=±%d (raw openDelta=%s poolOpen=%s)' % (oc, E, oc - E, T * KB40, c['openDelta'], c['poolOpen']))
            check('unit.%s.%s.T%d.countDelta' % (rep, tag, T), int(c['countDelta']) >= T, c['countDelta'])
            check('unit.%s.%s.T%d.closedDeltaC' % (rep, tag, T), abs(cc) <= T * KB40, 'closedDeltaC=%d band=±%d (raw closedDelta=%s poolClosed=%s)' % (cc, T * KB40, c['closedDelta'], c['poolClosed']))
            check('unit.%s.%s.T%d.released' % (rep, tag, T), c['afterClose'] == '{entries=0 own=none=%d}' % T and c['errors'] == '0', c['afterClose'])
    rd = readers.get('stale', {})
    check('unit.%s.stale.captured' % rep, rd.get('captured') == '262144' and rd.get('getterKiB') == '16384', 'captured=%s getterKiB=%s' % (rd.get('captured'), rd.get('getterKiB')))
    c = cycles.get(('stale', '8'), {})
    if c:
        check('unit.%s.stale.per_buffer' % rep, c['workers'] == '{entries=1 own=262144:direct=8}', c['workers'])
        oc = int(c['openDeltaC'])
        check('unit.%s.stale.openDeltaC' % rep, abs(oc - 8 * 262144) <= 8 * KB40, 'openDeltaC=%d E=%d (16 MiB buffers would give %d)' % (oc, 8 * 262144, 8 * 16777216))
        check('unit.%s.stale.released' % rep, c['afterClose'] == '{entries=0 own=none=8}' and c['errors'] == '0', c['afterClose'])
    else:
        check('unit.%s.stale' % rep, False, 'missing')
    l = sets.get(('gate', '512'), '')
    check('unit.%s.gate.set' % rep, l.endswith('ACCEPTED getterKiB=512'), l[l.find('v='):])
    rd = readers.get('gate', {})
    check('unit.%s.gate.captured' % rep, rd.get('captured') == 'none' and rd.get('chunkLength') == '1048576' and rd.get('sstables') == '1', 'captured=%s chunkLength=%s' % (rd.get('captured'), rd.get('chunkLength')))
    c = cycles.get(('gate', '8'), {})
    if c:
        check('unit.%s.gate.per_buffer' % rep, c['workers'] == '{entries=0 own=none=8}', c['workers'])
        check('unit.%s.gate.openDeltaC' % rep, int(c['openDeltaC']) <= 8 * 1.1 * MiB, 'openDeltaC=%s bound=%d (raw openDelta=%s poolOpen=%s)' % (c['openDeltaC'], 8 * 1.1 * MiB, c['openDelta'], c['poolOpen']))
    else:
        check('unit.%s.gate' % rep, False, 'missing')

# ---------------- cluster ----------------
CD = os.path.join(base, 'cluster-' + crun)
cl = open(os.path.join(CD, 'commands.log')).read().splitlines() if os.path.exists(os.path.join(CD, 'commands.log')) else []
setl = [l.split('SUMMARY ', 1)[1] for l in cl if 'SUMMARY SET ' in l]
comp = {}
for l in cl:
    m = re.search(r'SUMMARY COMPACT (\S+) rc=(\d+) client_start_ms=(\d+) client_end_ms=(\d+)', l)
    if m:
        comp[m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))


def setline(start, tag, v):
    for l in setl:
        if l.startswith('SET %s %s v=%s ' % (start, tag, v)):
            return l
    return ''


for v in ('255', '0'):
    l = setline('n1', 'reject', v)
    check('cluster.n1.reject.%s' % v, ('REJECTED %s ' % v) in l and 'IllegalArgumentException: compressed_read_ahead_buffer_size_in_kb must be at least 256KiB' in l and l.rstrip().endswith('now 256'), l[:300])
ARMS = {'v256': (256, None, 262144), 'v4096': (4096, None, 4194304), 'v16384': (16384, None, 16777216), 'v4096b': (4096, None, 4194304),
        'stale': (256, 16384, 262144), 'cc': (16384, None, None)}
for a, (v1, v2, cap) in ARMS.items():
    start = 'cc' if a == 'cc' else 'n1'
    l = setline(start, a + '-before-writes', v1)
    check('cluster.%s.set' % a, ('OK %d' % v1) in l and l.rstrip().endswith('now %d' % v1), l[-80:])
    if v2:
        l = setline(start, a + '-after-writes', v2)
        check('cluster.%s.set_after_writes' % a, ('OK %d' % v2) in l and l.rstrip().endswith('now %d' % v2), l[-80:])

for start, exp_sets, fc in (('n1', ['256', '4096', '16384', '4096', '256', '16384'], 'false'), ('cc', ['16384'], 'true')):
    sl = open(os.path.join(CD, start, 'system.log')).read() if os.path.exists(os.path.join(CD, start, 'system.log')) else ''
    got = re.findall(r'set compressed read ahead buffer size to (-?\d+)KiB', sl)
    check('cluster.%s.setlog' % start, got == exp_sets, 'INFO set lines %s (expected %s; none for 255/0)' % (got, exp_sets))
    cfg = re.search(r'Node configuration:\[(.*)', sl)
    cfg = cfg.group(1) if cfg else ''
    check('cluster.%s.readback' % start, 'DiskAccessMode is standard' in sl and 'compressed_read_ahead_buffer_size=256KiB' in cfg and ('file_cache_enabled=%s' % fc) in cfg,
          'standard=%s knob256=%s file_cache_enabled=%s' % ('DiskAccessMode is standard' in sl, 'compressed_read_ahead_buffer_size=256KiB' in cfg, fc))

traces = {}
for start in ('n1', 'cc'):
    p = os.path.join(CD, start, 'readahead.trace')
    traces[start] = [dict(re.findall(r'(\w+)=(\S+)', l), kind=l.split(' ', 1)[0]) for l in open(p).read().splitlines()] if os.path.exists(p) else []


def poll(a):
    rows = []
    p = os.path.join(CD, a, 'poll.csv')
    for l in (open(p).read().splitlines() if os.path.exists(p) else []):
        f = l.split(',')
        if len(f) == 3 and f[0].isdigit():
            rows.append((int(f[0]), int(f[1]), int(f[2])))
    return rows


peaks = {}
for a, (v1, v2, cap) in ARMS.items():
    start = 'cc' if a == 'cc' else 'n1'
    rc, t0, t1 = comp.get(a, (None, 0, 0))
    check('cluster.%s.compact' % a, rc == 0, 'rc=%s window=%d ms' % (rc, t1 - t0))
    tb = open(os.path.join(CD, a, 'tablestats-before.txt')).read() if os.path.exists(os.path.join(CD, a, 'tablestats-before.txt')) else ''
    ta = open(os.path.join(CD, a, 'tablestats-after.txt')).read() if os.path.exists(os.path.join(CD, a, 'tablestats-after.txt')) else ''
    nb = re.search(r'SSTable count: (\d+)', tb); na = re.search(r'SSTable count: (\d+)', ta); ratio = re.search(r'SSTable Compression Ratio: ([-\d.]+)', tb)
    check('cluster.%s.sstables' % a, bool(nb and na and ratio) and nb.group(1) == '16' and na.group(1) == '1' and 0 < float(ratio.group(1)) < 1,
          'before=%s after=%s ratio=%s' % (nb and nb.group(1), na and na.group(1), ratio and ratio.group(1)))
    own = lambda f: ('/ra_%s/standard1-' % a) in f and f.endswith('-Data.db')
    al = [e for e in traces[start] if e['kind'] == 'alloc' and own(e.get('file', ''))]
    fr = [e for e in traces[start] if e['kind'] == 'free' and own(e.get('file', ''))]
    if cap is None:
        check('cluster.%s.no_readahead' % a, len(al) == 0, 'alloc lines for ra_%s data files: %d' % (a, len(al)))
    else:
        caps = sorted({e['cap'] for e in al}); thr = sorted({e['thread'] for e in al}); dr = sorted({e['direct'] for e in al})
        inwin = all(t0 <= int(e['ms']) <= t1 for e in al)
        files_a = sorted(e['file'] for e in al); files_f = sorted(e['file'] for e in fr)
        check('cluster.%s.per_buffer' % a, len(al) == 16 and caps == [str(cap)] and dr == ['true'] and len(thr) == 1 and thr[0].startswith('CompactionExecutor') and inwin,
              'alloc=%d caps=%s direct=%s threads=%s in_window=%s' % (len(al), caps, dr, thr, inwin))
        check('cluster.%s.freed' % a, len(fr) == 16 and files_a == files_f and sorted({e['thread'] for e in fr}) == thr, 'free=%d same_files=%s' % (len(fr), files_a == files_f))
    other = [e for e in traces[start] if e['kind'] == 'alloc' and not own(e.get('file', '')) and t0 <= int(e['ms']) <= t1]
    info('cluster.%s.other_alloc_in_window' % a, '%d (%s)' % (len(other), sorted({e['cap'] for e in other})))
    rows = poll(a)
    b = [u for t, u, c in rows if t < t0]; w = [u for t, u, c in rows if t0 <= t <= t1]; af = [u for t, u, c in rows if t >= t1 + 5000]
    if len(b) >= 3 and len(w) >= 3 and len(af) >= 3:
        bl = statistics.median(b); pk = max(w) - bl; aft = statistics.median(af) - bl
        peaks[a] = pk
        check('cluster.%s.samples' % a, True, 'baseline=%d window=%d after=%d samples; baseline %.2f MiB spread %.2f MiB' % (len(b), len(w), len(af), bl / MiB, (max(b) - min(b)) / MiB))
        if a != 'cc':
            check('cluster.%s.after' % a, abs(aft) <= 8 * MiB, 'peak %.2f MiB, after %.2f MiB' % (pk / MiB, aft / MiB))
        else:
            info('cluster.cc.jmx', 'peak %.2f MiB, after %.2f MiB (INFO only, B3h)' % (pk / MiB, aft / MiB))
    else:
        check('cluster.%s.samples' % a, False, 'baseline=%d window=%d after=%d' % (len(b), len(w), len(af)))


def band(name, x, lo, hi):
    if x is None:
        check(name, False, 'missing peak'); return
    check(name, lo * MiB <= x <= hi * MiB, '%.2f MiB in [%.1f, %.1f]' % (x / MiB, lo, hi))


g = peaks.get
d = lambda x, y: (g(x) - g(y)) if g(x) is not None and g(y) is not None else None
for b4 in ('v4096', 'v4096b'):
    band('cluster.peak(%s)-peak(v256)' % b4, d(b4, 'v256'), 51, 69)
    band('cluster.peak(v16384)-peak(%s)' % b4, d('v16384', b4), 163.2, 220.8)
band('cluster.|peak(stale)-peak(v256)|', abs(d('stale', 'v256')) if d('stale', 'v256') is not None else None, 0, 9)
band('cluster.peak(v16384)-peak(stale)', d('v16384', 'stale'), 214.2, 289.8)

print('RESULT %d of %d checks hold' % (sum(res), len(res)))
