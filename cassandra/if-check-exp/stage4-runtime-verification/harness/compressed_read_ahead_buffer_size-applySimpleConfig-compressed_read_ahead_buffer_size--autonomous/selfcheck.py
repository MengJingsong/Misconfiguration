#!/usr/bin/env python3
"""Independent self-check of run 1 of compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous
(results §5). Written before the run-1 readings were read. Re-reads the raw files only, never summary.txt:
  unit:    p1-<v>.out (ConfigProbe output), stage4.out (the probe's STAGE4 lines, written by the test JVM)
  cluster: per start <start>/readahead.trace (Byteman), <start>/jmx.csv (sampler), <start>/system.log, <start>/node.out,
           <start>/tablestats-before.txt / -after.txt; and commands.log only for what no other file holds (the refusal exit code,
           the nodetool compact exit code and client window, the CrabJmx get/set output), each a line the runner wrote there.
Re-derives every B2f / B3f clause (as amended 2026-10-25, with runbook fix D1) and prints one line per check:
  CHECK <ok|FAIL> <name> :: <detail>        and INFO lines that decide nothing.
usage: selfcheck.py <unit log dir> <cluster log dir>"""
import os, re, statistics, sys

U, K = sys.argv[1], sys.argv[2]
n_ok = n_fail = 0
KiB, MiB = 1024, 1024 * 1024
SLACK, OTHER = 64 * KiB, 9 * MiB


def check(name, cond, detail=''):
    global n_ok, n_fail
    if cond:
        n_ok += 1
    else:
        n_fail += 1
    print('CHECK %s %s :: %s' % ('ok' if cond else 'FAIL', name, detail))


def info(name, detail):
    print('INFO %s :: %s' % (name, detail))


def read(p):
    try:
        return open(p, errors='replace').read()
    except FileNotFoundError:
        return ''


# ---------------- unit: ConfigProbe ----------------
MSG = 'REJECT ConfigurationException: compressed_read_ahead_buffer_size must be at least 256KiB (set to 0 to disable), but was %s'
P1 = {'0KiB': 'OK getCompressedReadAheadBufferSize=0', '1KiB': MSG % '1KiB', '255KiB': MSG % '255KiB',
      '256KiB': 'OK getCompressedReadAheadBufferSize=262144', 'unset': 'OK getCompressedReadAheadBufferSize=262144'}
for v, exp in P1.items():
    lines = [l for l in read(os.path.join(U, 'p1-%s.out' % v)).splitlines() if l.startswith(('OK ', 'REJECT '))]
    got = lines[0] if lines else '(none)'
    check('unit.p1.%s' % v, got.startswith(exp), got[:220])

# ---------------- unit: ReadAheadProbeTest ----------------
S4 = read(os.path.join(U, 'stage4.out')).splitlines()
# arm: (B, file cache, chunk length); 256KiB-chunk256 replaces the 16KiB arm (runbook defect D2)
ARMS = {'0KiB': (0, False, 16384), '256KiB-chunk256': (262144, False, 262144), '256KiB': (262144, False, 16384),
        '4096KiB': (4194304, False, 16384), 'ctl-cache': (4194304, True, 16384)}


def kv(s):
    return dict(re.findall(r'(\w+)=(\S+)', s))


dclose16 = {}
for arm, (B, cache, chunk) in ARMS.items():
    rb = [l for l in S4 if l.startswith('STAGE4 readback label=%s ' % arm)]
    if len(rb) != 1:
        check('unit.%s.readback' % arm, False, '%d readback lines' % len(rb)); continue
    r = kv(rb[0])
    fac = re.search(r'factories=\{([^}]*)\}', rb[0]).group(1)
    expfac = 'ChunkCache$CachingRebufferer=16' if cache else 'CompressedChunkReader$Standard=16'
    check('unit.%s.readback' % arm, int(r['B']) == B and r['fileCacheEnabled'] == str(cache).lower() and r['chunkCacheInstance'] == str(cache).lower()
          and r['diskAccessMode'] == 'standard' and r['sstables'] == '16' and r['chunkLength'] == 'true/%d' % chunk and fac == expfac,
          'B=%s fileCache=%s chunkCache=%s mode=%s sstables=%s chunk=%s factories={%s}' % (r['B'], r['fileCacheEnabled'], r['chunkCacheInstance'],
                                                                                        r['diskAccessMode'], r['sstables'], r['chunkLength'], fac))
    sized = (B > chunk) and not cache
    for phase, k in (('k16', 16), ('k1', 1)):
        cl = [l for l in S4 if l.startswith('STAGE4 cycle label=%s phase=%s ' % (arm, phase))]
        if len(cl) != 1:
            check('unit.%s.%s' % (arm, phase), False, '%d lines' % len(cl)); continue
        line = cl[0]
        head, before, opn, closed = [x.strip() for x in line.split('|')]
        h, o, c = kv(head), kv(opn), kv(closed)
        caps = re.search(r'caps=\[([^\]]*)\]', opn).group(1)
        nexp = k if sized else 0
        # amendment D2: a chunk larger than BufferPool's 128 KiB normal chunk makes each scanner's rebufferer buffer a direct
        # allocation freed on close (BufferPool.java:906-925, 810-819)
        E = nexp * B + (k * chunk if chunk > 131072 else 0)
        dopen, dclose = int(h['d_open']), int(h['d_close'])
        check('unit.%s.%s.per_buffer' % (arm, phase),
              int(o['live']) == nexp and int(o['own']) == nexp and (caps == ('%dx%d' % (B, nexp)) if nexp else caps == '')
              and (o['direct'] == 'all' if nexp else o['direct'] == 'na') and int(c['live']) == 0,
              'open live=%s own=%s caps=[%s] direct=%s; closed live=%s; expected %d x %d' % (o['live'], o['own'], caps, o['direct'], c['live'], nexp, B))
        check('unit.%s.%s.d_close' % (arm, phase), abs(dclose - E) <= SLACK, 'd_close=%d E=%d diff=%d (band +-%d)' % (dclose, E, dclose - E, SLACK))
        check('unit.%s.%s.d_open' % (arm, phase), E - SLACK <= dopen <= E + OTHER, 'd_open=%d E=%d (band [E-64KiB, E+9MiB])' % (dopen, E))
        check('unit.%s.%s.scanned' % (arm, phase), int(h['partitions']) == k, 'partitions=%s' % h['partitions'])
        if phase == 'k16':
            dclose16[arm] = dclose
        else:
            d16 = dclose16.get(arm)
            if d16 is not None:
                check('unit.%s.total_k16_vs_k1' % arm, abs(d16 - 16 * dclose) <= 17 * SLACK, 'd_close k16=%d, 16 x k1=%d' % (d16, 16 * dclose))
    pr = [l for l in S4 if l.startswith('STAGE4 pointread label=%s ' % arm)]
    info('unit.%s.pointread' % arm, pr[0][len('STAGE4 pointread '):] if pr else 'missing')
    check('unit.%s.done' % arm, any(l.startswith('STAGE4 done label=%s' % arm) for l in S4))
if '256KiB' in dclose16 and '4096KiB' in dclose16:
    check('unit.knob_changes_total', dclose16['4096KiB'] - dclose16['256KiB'] > 16 * (4194304 - 262144) - 2 * SLACK,
          'd_close k16: 256KiB=%d 4096KiB=%d' % (dclose16['256KiB'], dclose16['4096KiB']))

# ---------------- cluster ----------------
CMD = read(os.path.join(K, 'commands.log'))
z = re.search(r'SUMMARY REFUSAL z100 rc=(\d+) secs=(\d+)', CMD)
zt = read(os.path.join(K, 'z100', 'node.out')) + read(os.path.join(K, 'z100', 'system.log'))
check('cluster.z100.refused', z is not None and z.group(1) == '3' and int(z.group(2)) <= 120 and 'Startup complete' not in zt
      and 'compressed_read_ahead_buffer_size must be at least 256KiB (set to 0 to disable), but was 100KiB' in zt,
      'rc=%s secs=%s message=%s' % (z.group(1) if z else '?', z.group(2) if z else '?', 'but was 100KiB' in zt))

STARTS = {'c0': (0, 32, False), 'c256': (262144, 32, False), 'c16m': (16777216, 32, False), 'ctl-cache': (16777216, 32, True), 'ctl-k4': (16777216, 4, False)}
own = lambda f: '/keyspace1/standard1-' in f and f.endswith('-Data.db')
res = {}
for st, (B, kexp, cache) in STARTS.items():
    D = os.path.join(K, st)
    slog = read(os.path.join(D, 'system.log'))
    cfg = re.search(r'Node configuration:\[(.*)\]', slog)
    cfg = cfg.group(1) if cfg else ''
    bset = re.search(r'compressed_read_ahead_buffer_size=([^;]*)', cfg)
    fce = re.search(r'file_cache_enabled=([^;]*)', cfg)
    getv = re.search(r'SUMMARY READBACK %s DiskAccessMode is (\w+).*?jmx GET CompressedReadAheadBufferInKB=(\d+)' % re.escape(st), CMD)
    check('cluster.%s.readback' % st, bset is not None and fce is not None and fce.group(1) == str(cache).lower() and getv is not None
          and getv.group(1) == 'standard' and int(getv.group(2)) * 1024 == B and 'Startup complete' in slog,
          'cfg %s file_cache_enabled=%s; DiskAccessMode %s; jmx KiB %s' % (bset.group(1) if bset else '?', fce.group(1) if fce else '?',
                                                                          getv.group(1) if getv else '?', getv.group(2) if getv else '?'))
    tb, ta = read(os.path.join(D, 'tablestats-before.txt')), read(os.path.join(D, 'tablestats-after.txt'))
    kb = re.search(r'SSTable count: (\d+)', tb); ka = re.search(r'SSTable count: (\d+)', ta)
    ratio = re.search(r'SSTable Compression Ratio: (-?[\d.]+)', tb)
    k = int(kb.group(1)) if kb else -1
    check('cluster.%s.sstables' % st, k == kexp and ratio is not None and 0 < float(ratio.group(1)) < 1,
          'before k=%d ratio=%s (expected k=%d, ratio in (0,1))' % (k, ratio.group(1) if ratio else '?', kexp))
    cm = re.search(r'SUMMARY COMPACT %s rc=(\d+) client_start_ms=(\d+) client_end_ms=(\d+)' % re.escape(st), CMD)
    check('cluster.%s.compaction' % st, cm is not None and cm.group(1) == '0' and ka is not None and ka.group(1) == '1',
          'rc=%s after k=%s' % (cm.group(1) if cm else '?', ka.group(1) if ka else '?'))
    t0, t1 = (int(cm.group(2)), int(cm.group(3))) if cm else (0, 0)
    # trace
    tl = read(os.path.join(D, 'readahead.trace')).splitlines()
    A = [kv(l) for l in tl if l.startswith('alloc ')]
    F = [kv(l) for l in tl if l.startswith('free ')]
    oa = [a for a in A if own(a['file'])]; of = [f for f in F if own(f['file'])]
    sized = B > 16384 and not cache
    if sized:
        threads = {a['thread'] for a in oa} | {f['thread'] for f in of}
        ev = sorted([(int(a['ms']), 1) for a in oa] + [(int(f['ms']), -1) for f in of])
        live = mx = 0
        for _, d in ev:
            live += d; mx = max(mx, live)
        inwin = all(t0 - 1000 <= int(a['ms']) <= t1 + 1000 for a in oa + of)
        check('cluster.%s.per_buffer' % st,
              len(oa) == k and all(int(a['cap']) == B and int(a['knob']) == B and a['direct'] == 'true' for a in oa) and len(threads) == 1
              and all(t.startswith('CompactionExecutor') for t in threads) and len(of) == len(oa) and mx == k and len({a['file'] for a in oa}) == k and inwin,
              'own alloc=%d free=%d distinct files=%d caps=%s threads=%s max_live=%d in_window=%s (k=%d, B=%d)' % (
                  len(oa), len(of), len({a['file'] for a in oa}), sorted({(a['cap'], a['direct']) for a in oa}), sorted(threads), mx, inwin, k, B))
        first, last = min(int(a['ms']) for a in oa) if oa else 0, max(int(f['ms']) for f in of) if of else 0
    else:
        check('cluster.%s.no_buffer' % st, len(A) == 0, 'alloc lines (any file)=%d own=%d' % (len(A), len(oa)))
        first, last = t0, t1
    info('cluster.%s.other_files' % st, 'other alloc=%d free=%d threads=%s' % (len(A) - len(oa), len(F) - len(of),
                                                                             sorted({re.sub(r'[-:]\d+$', '', a['thread']) for a in A if not own(a['file'])})))
    # jmx
    rows = []
    for l in read(os.path.join(D, 'jmx.csv')).splitlines()[1:]:
        p = l.split(',')
        if len(p) == 6 and p[3].isdigit():
            rows.append((int(p[0]), p[1], int(p[2]), int(p[3])))
    base = [r[3] for r in rows if r[1] == 'baseline']
    post = [r for r in rows if r[1] in ('compact', 'after')]
    if not base or not post:
        check('cluster.%s.jmx' % st, False, 'no samples'); continue
    b = statistics.median(base)
    peak = max(post, key=lambda r: r[3])
    dpeak = peak[3] - b
    endt = rows[-1][0]
    dafter = statistics.median([r[3] for r in rows if r[0] >= endt - 5000]) - b
    nwin = len([r for r in rows if first <= r[0] <= last])
    # other-file read-ahead buffers live at the peak's time
    oev = sorted([(int(a['ms']), 1, int(a['cap'])) for a in A if not own(a['file'])] + [(int(f['ms']), -1, int(f['knob'])) for f in F if not own(f['file'])])
    olive = 0
    for t, d, c in oev:
        if t <= peak[0]:
            olive += d * c
    res[st] = dict(dpeak=dpeak, dafter=dafter, olive=olive, k=k, B=B, nwin=nwin)
    info('cluster.%s.jmx' % st, 'baseline=%d dpeak=%d (%.1f MiB) at %d dafter=%d (%.1f MiB) other_live_at_peak=%d samples_in_window=%d samples=%d' % (
        b, dpeak, dpeak / MiB, peak[0], dafter, dafter / MiB, olive, nwin, len(rows)))
    if sized:
        check('cluster.%s.samples_in_window' % st, nwin >= 3, 'samples between first alloc and last free: %d' % nwin)
    if not cache:
        check('cluster.%s.released' % st, dafter <= OTHER, 'dafter=%d (<= 9 MiB)' % dafter)

if 'c0' in res:
    c0 = res['c0']
    check('cluster.c0.dpeak', c0['dpeak'] <= OTHER, 'dpeak=%d (<= 9 MiB)' % c0['dpeak'])
    for st in ('c16m', 'ctl-k4', 'c256'):
        if st in res:
            r = res[st]; E = r['k'] * r['B']
            x = r['dpeak'] - c0['dpeak'] - r['olive']
            txt = 'dpeak - dpeak(c0) - other = %d (%.1f MiB), E = %d (%.1f MiB), diff %.1f MiB (band +-9 MiB)' % (x, x / MiB, E, E / MiB, (x - E) / MiB)
            if st == 'c256':
                info('cluster.c256.jmx_band', txt + ' [INFO: band as wide as E]')
            else:
                check('cluster.%s.jmx_band' % st, abs(x - E) <= OTHER, txt)
    if 'ctl-cache' in res:
        info('cluster.ctl-cache.jmx', 'dpeak=%.1f MiB dafter=%.1f MiB (chunk cache pool; INFO)' % (res['ctl-cache']['dpeak'] / MiB, res['ctl-cache']['dafter'] / MiB))

sets = re.findall(r'SUMMARY SETTER c0 (SET \d+ \S+.*?GET CompressedReadAheadBufferInKB=\d+)', CMD)
info('cluster.c0.setter', ' || '.join(sets) if sets else 'missing')
fin = re.findall(r'SUMMARY final CassandraDaemon processes: (.*)', CMD)
check('cluster.final_no_process', bool(fin) and fin[-1].strip() == 'none', fin[-1] if fin else 'missing')

print('RESULT %d ok, %d fail' % (n_ok, n_fail))
