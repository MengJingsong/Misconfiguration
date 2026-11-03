#!/usr/bin/env python3
"""Independent self-check (results §5) of coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous.
usage: selfcheck.py <unit stage4.out> <cluster log dir>
Re-parses the raw files only (never summary.txt or summarize.py output) and re-derives every B2f and B3f clause of the
frozen case file (sha256 4f2657bc...). Prints 'CHECK <id> <holds|FAILS> <detail>' and 'INFO ...', then a count.
Bucket offsets are recomputed here from EstimatedHistogram.newOffsets (164 buckets, x1.2, Math.round)."""
import bisect, datetime, glob, json, math, os, re, statistics, sys

UNIT, CL = sys.argv[1], sys.argv[2]
res = []


def check(cid, ok, detail=''):
    res.append(ok)
    print('CHECK %s %s %s' % (cid, 'holds' if ok else 'FAILS', detail))


def info(s):
    print('INFO ' + s)


# --- bucket offsets (DecayingEstimatedHistogramReservoir default, considerZeroes=false)
OFF = [1]
while len(OFF) < 164:
    n = math.floor(OFF[-1] * 1.2 + 0.5)
    OFF.append(n if n != OFF[-1] else n + 1)


def bucket(v):
    return OFF[bisect.bisect_left(OFF, v)]


S = 65544
KIB = 1024; MIB = 1024 * 1024

# ======================= unit tier =======================
rows = {}
mirror = None
v1101 = {}
for line in open(UNIT):
    if line.startswith('STAGE4 row '):
        d = dict(t.split('=', 1) for t in line.split()[2:] if '=' in t)
        rows[d['name']] = d
    elif line.startswith('STAGE4 mirror '):
        mirror = dict(t.split('=', 1) for t in line.split()[2:] if '=' in t)
    elif line.startswith('STAGE4 v1101 '):
        parts = line.rstrip('\n').split(' ', 3)
        v1101[parts[2]] = parts[3] if len(parts) > 3 else ''
    elif line.startswith('STAGE4 info jvm'):
        info('unit ' + line.strip())
        check('unit.alloc_supported', 'allocSupported=true allocEnabled=true' in line, line.strip()[-80:])

hs = [int(x) for x in mirror['h'].strip('[]').split(',')]
b0 = int(mirror['b0'])
check('u1.h_equal', len(hs) == 1, 'h=%s' % hs)
h = hs[0]
check('u1.h_range', 65536 < h < 66560, 'h=%d' % h)


def k_of(T):
    k = 1
    while b0 + k * h < T:
        k += 1
    return k


for T, kk in ((262144, 4), (1048576, 16), (4194304, 64)):
    check('u1.k_%d' % T, k_of(T) == kk, 'k=%d expected %d' % (k_of(T), kk))
check('unit.rows_present', len(rows) == 15, 'n=%d' % len(rows))


def I(d, k):
    return int(d[k])


S16 = I(rows['N_P16'], 'len'); S64 = I(rows['N_P64'], 'len')
for P, d in ((16, rows['N_P16']), (64, rows['N_P64'])):
    n = 'u2.N_P%d' % P
    check(n + '.readback', d['rb_enabled'] == 'true' and d['rb_coord'] == 'null' and d['rb_local'] == 'null', '')
    check(n + '.rows', I(d, 'rows') == 128 and d['err'] == '-', 'rows=%s err=%s' % (d['rows'], d['err']))
    check(n + '.coordMax', I(d, 'coordMax') == bucket(P * S), '%s vs %d' % (d['coordMax'], bucket(P * S)))
    check(n + '.local0', I(d, 'localMax') == 0 and I(d, 'coordAborts') == 0 and I(d, 'localAborts') == 0, '')
    ln, cp, al = I(d, 'len'), I(d, 'cap'), I(d, 'alloc')
    check(n + '.len_band', P * 65536 <= ln <= P * 65600 + 512, 'len=%d' % ln)
    check(n + '.cap_band', ln <= cp <= 2 * ln + 65664 + 4096, 'cap=%d' % cp)
    check(n + '.alloc', al >= 2 * P * 65536, 'alloc=%d' % al)
check('u2.len_scales', S64 >= 3.9 * S16, 'S64/S16=%.3f' % (S64 / S16))
Sof = {16: S16, 64: S64}
for T in (262144, 1048576, 4194304):
    m = T // S + 1
    for P in (16, 64):
        d = rows['C_%d_P%d' % (T, P)]; n = 'u3.C_%d_P%d' % (T, P)
        check(n + '.readback', d['rb_enabled'] == 'true' and d['rb_coord'] == str(T) and d['rb_local'] == 'null', '')
        refused = (P - 1) * S > T
        if refused:
            check(n + '.refused', I(d, 'rows') == 0 and d['err'] == 'ReadFailureException' and '=4}' in d['codes'] and I(d, 'coordAborts') == 1,
                  'rows=%s err=%s codes=%s aborts=%s' % (d['rows'], d['err'], d['codes'], d['coordAborts']))
            check(n + '.coordMax', I(d, 'coordMax') == bucket(m * S), '%s vs bucket(%d)=%d' % (d['coordMax'], m * S, bucket(m * S)))
        else:
            check(n + '.not_refused', I(d, 'rows') == 128 and d['err'] == '-' and I(d, 'coordAborts') == 0, 'rows=%s err=%s' % (d['rows'], d['err']))
            check(n + '.coordMax', I(d, 'coordMax') == bucket(P * S), '%s vs %d' % (d['coordMax'], bucket(P * S)))
        check(n + '.localAborts0', I(d, 'localAborts') == 0, '')
        check(n + '.replica_same_as_N', d['s3'] == 'ok' and I(d, 'len') == Sof[P], 'len=%s N=%d' % (d['len'], Sof[P]))
        check(n + '.cap_alloc_band', I(d, 'len') <= I(d, 'cap') <= 2 * I(d, 'len') + 65664 + 4096 and I(d, 'alloc') >= 2 * P * 65536,
              'cap=%s alloc=%s' % (d['cap'], d['alloc']))
for T in (262144, 1048576, 4194304):
    k = k_of(T); X = b0 + k * h
    allocs = {}
    for P in (16, 64):
        d = rows['L_%d_P%d' % (T, P)]; n = 'u4.L_%d_P%d' % (T, P)
        check(n + '.readback', d['rb_enabled'] == 'true' and d['rb_coord'] == 'null' and d['rb_local'] == str(T), '')
        check(n + '.coordAborts0', I(d, 'coordAborts') == 0, '')
        if k <= P:
            check(n + '.refused', I(d, 'rows') == 0 and d['err'] == 'ReadFailureException' and '=4}' in d['codes'] and I(d, 'localAborts') == 1,
                  'rows=%s err=%s codes=%s aborts=%s' % (d['rows'], d['err'], d['codes'], d['localAborts']))
            check(n + '.localMax', I(d, 'localMax') == bucket(X), '%s vs bucket(%d)=%d' % (d['localMax'], X, bucket(X)))
            check(n + '.s3_throws_X', d['s3'] == 'LocalReadSizeTooLargeException' and I(d, 'X') == X and T <= X < T + h, 'X=%s pred=%d' % (d['X'], X))
            check(n + '.alloc_bound', I(d, 'alloc') < 5 * T + MIB, 'alloc=%s bound=%d' % (d['alloc'], 5 * T + MIB))
            allocs[P] = I(d, 'alloc')
        else:
            check(n + '.not_refused', I(d, 'rows') == 128 and d['err'] == '-' and I(d, 'localAborts') == 0, 'rows=%s' % d['rows'])
            check(n + '.localMax', I(d, 'localMax') == bucket(b0 + P * h), '%s vs %d' % (d['localMax'], bucket(b0 + P * h)))
            check(n + '.s3_completes', d['s3'] == 'ok' and I(d, 'len') == Sof[P], 'len=%s' % d['len'])
    if len(allocs) == 2:
        r = allocs[64] / allocs[16]
        check('u4.L_%d.alloc_same_P' % T, 1 / 1.1 <= r <= 1.1, 'ratio=%.3f' % r)
d = rows['OFF_262144_P16']
check('u5.readback', d['rb_enabled'] == 'false' and d['rb_coord'] == '262144' and d['rb_local'] == '262144', '')
check('u5.no_abort', I(d, 'rows') == 128 and d['err'] == '-' and I(d, 'coordMax') == 0 and I(d, 'localMax') == 0
      and I(d, 'coordAborts') == 0 and I(d, 'localAborts') == 0, 'rows=%s coordMax=%s localMax=%s' % (d['rows'], d['coordMax'], d['localMax']))
check('u5.s3_throws', d['s3'] == 'LocalReadSizeTooLargeException' and I(d, 'X') == b0 + k_of(262144) * h, 'X=%s' % d['X'])
for w in ('coordinator_read_size', 'local_read_size', 'row_index_read_size'):
    msg = '%s_fail_threshold (1KiB) must be greater than or equal to %s_warn_threshold (2KiB)' % (w, w)
    check('u6.%s.reject' % w, v1101.get(w + '-fail1KiB-warn2KiB', '') == 'threw ConfigurationException: ' + msg, v1101.get(w + '-fail1KiB-warn2KiB'))
    check('u6.%s.accept21' % w, v1101.get(w + '-fail2KiB-warn1KiB', '').startswith('accepted'), '')
    check('u6.%s.accept11' % w, v1101.get(w + '-fail1KiB-warn1KiB', '').startswith('accepted'), '')
    check('u6.%s.setter_bypass' % w, v1101.get('setter-' + w, '') == 'accepted fail=1KiB warn=2KiB', v1101.get('setter-' + w))

# ======================= cluster tier =======================
if CL == '-':
    print('SUMMARY %d of %d checks hold' % (sum(res), len(res)))
    sys.exit(0)


def wall_ms(stamp):
    return int(datetime.datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000)


phases = [l.split() for l in open(os.path.join(CL, 'phases.txt'))]
kvd = lambda toks: dict(t.split('=', 1) for t in toks if '=' in t)


def gc(arm):
    young, full, hum = [], [], {}
    lines = []
    for g in sorted(glob.glob(os.path.join(CL, arm, 'gc.log.*'))) + [os.path.join(CL, arm, 'gc.log')]:  # all rotated parts (fix 2026-10-25)
        lines += open(g, errors='replace').readlines()
    for line in lines:
        m = re.match(r'\[([^\]]+)\]', line)
        if not m:
            continue
        try:
            t = wall_ms(m.group(1))
        except ValueError:
            continue
        for kind, lst in (('Young', young), ('Full', full)):
            g = re.search(r'GC\((\d+)\) Pause %s .*? (\d+)M->(\d+)M\((\d+)M\)' % kind, line)
            if g:
                lst.append((t, int(g.group(1)), int(g.group(3))))
        g = re.search(r'GC\((\d+)\) Humongous regions: (\d+)->(\d+)', line)
        if g:
            hum[int(g.group(1))] = int(g.group(3))
    return young, full, hum


def queries(arm, P):
    out = []
    for f in sorted(glob.glob(os.path.join(CL, arm, 'read-P%d' % P, 'w*.lines'))):
        for line in open(f, errors='replace'):
            if line.startswith('q '):
                head = line.split(' msg=')[0]
                out.append(dict(t.split('=', 1) for t in head.split()[1:]))
    return out


def meters(arm, tag, P):
    out = {}
    for line in open(os.path.join(CL, arm, 'meters-%s-P%d.txt' % (tag, P))):
        p = line.strip().split('|')
        if len(p) == 3:
            out[p[0].split('name=')[-1] + '.' + p[1]] = float(p[2])
    return out


R = {}
for arm, cfg in (('N', {}), ('C', {'coordinator_read_size_fail_threshold': '1MiB'}), ('L', {'local_read_size_fail_threshold': '1MiB'}),
                 ('L4', {'local_read_size_fail_threshold': '4MiB'})):
    st = json.load(open(os.path.join(CL, arm, 'settings.json')))
    jm = {l.split('|')[1]: l.strip().split('|')[2] for l in open(os.path.join(CL, arm, 'jmx-readback.txt')) if l.count('|') == 2}
    ok = st.get('read_thresholds_enabled') == 'true' and jm.get('ReadThresholdsEnabled') == 'true'
    for name, jattr in (('coordinator_read_size_fail_threshold', 'CoordinatorLargeReadAbortThreshold'),
                        ('local_read_size_fail_threshold', 'LocalReadTooLargeAbortThreshold')):
        want = cfg.get(name)
        ok = ok and (st.get(name) == want) and ((jm.get(jattr) in ('null', '', None)) if want is None else jm.get(jattr) == want)
    for name in ('coordinator_read_size_warn_threshold', 'local_read_size_warn_threshold', 'row_index_read_size_fail_threshold'):
        ok = ok and st.get(name) is None
    check('V.%s.readback' % arm, ok, 'settings=%s jmx=%s' % ({k: st.get(k) for k in st if 'threshold' in k and st.get(k)}, jm))
    young, full, hum = gc(arm)
    idle = kvd(next(p for p in phases if p[0] == arm and p[1] == 'idle'))
    fb = [x for x in full if x[0] >= int(idle['t_gc'])]
    check('V.%s.baseline_gc' % arm, len(fb) >= 1, 'full GCs after idle=%d' % len(fb))
    baseB, baseb = (fb[0][2], hum.get(fb[0][1], 0)) if fb else (None, None)
    trace = []
    for line in open(os.path.join(CL, arm, 'vrt.trace'), errors='replace'):
        m = re.search(r'ms=(\d+)', line)
        if m:
            trace.append((int(m.group(1)), line))
    for P in (128, 512):
        ph = kvd(next(p for p in phases if p[0] == arm and p[1] == 'read' and p[2] == 'P=%d' % P))
        ts, tr = int(ph['t_start']), int(ph['returned'])
        q = queries(arm, P)
        win = [x for x in young if ts + 60000 <= x[0] <= ts + 180000]
        Bs = [x[2] for x in win]; bs = [hum.get(x[1], 0) for x in win]
        tl = [l for (t, l) in trace if ts - 2000 <= t <= tr + 2000]
        rb = [(int(re.search(r'len=(\d+)', l).group(1)), int(re.search(r'cap=(\d+)', l).group(1))) for l in tl if l.startswith('resp-buf len=')]
        fullp = [x for x in rb if x[0] >= (P - 1) * 65536]
        ra = [int(re.search(r'bytes=(-?\d+)', l).group(1)) for l in tl if l.startswith('read-alloc')]
        gf = [tuple(int(v) for v in re.search(r'size=(\d+) limit=(\d+)', l).groups()) for l in tl if l.startswith('guard-fail')]
        la = [int(x) for l in tl if l.startswith('local-abort') for x in re.findall(r'attempted to read (\d+) bytes', l)]
        mb, ma = meters(arm, 'before', P), meters(arm, 'after', P)
        R[(arm, P)] = dict(
            n=len(q), ok=sum(1 for x in q if x['outcome'] == 'OK'), err=[x for x in q if x['outcome'] == 'ERR'],
            dB=(statistics.median(Bs) - baseB) if Bs and baseB is not None else None,
            dH=(statistics.median(bs) - baseb) if bs and baseb is not None else None, npause=len(win),
            full=fullp, nrb=len(rb), ra=ra, gf=gf, la=la,
            dca=ma['CoordinatorReadSizeAborts.Count'] - mb['CoordinatorReadSizeAborts.Count'],
            dla=ma['LocalReadSizeAborts.Count'] - mb['LocalReadSizeAborts.Count'],
            cmax=ma['CoordinatorReadSize.Max'], lmax=ma['LocalReadSize.Max'])
        r = R[(arm, P)]
        info('%s P=%d queries=%d ok=%d err=%d pauses=%d dB=%s dH=%s resp_buf=%d full=%d ra_n=%d ra_med=%s gf=%d la=%d dca=%d dla=%d cmax=%d lmax=%d'
             % (arm, P, r['n'], r['ok'], len(r['err']), r['npause'], r['dB'], r['dH'], r['nrb'], len(fullp), len(ra),
                statistics.median(ra) if ra else None, len(gf), len(la), r['dca'], r['dla'], r['cmax'], r['lmax']))
        check('V.%s.P%d.queries' % (arm, P), r['n'] >= 50, 'n=%d' % r['n'])
        check('V.%s.P%d.pauses_in_window' % (arm, P), r['npause'] >= 1, 'n=%d' % r['npause'])

med = lambda xs: statistics.median(xs) if xs else None


def refused_all(r, code_ok=True):
    return r['ok'] == 0 and all(e.get('cls') == 'ReadFailure' and e.get('codes', '').endswith(':4') for e in r['err'])


for P in (128, 512):
    n = R[('N', P)]
    check('n1.P%d.no_aborts' % P, n['dca'] == 0 and n['dla'] == 0 and not any(e.get('cls') == 'ReadFailure' for e in n['err']),
          'dca=%d dla=%d errs=%d' % (n['dca'], n['dla'], len(n['err'])))
    fl = med([x[0] for x in n['full']]); fc = med([x[1] for x in n['full']])
    check('n2.P%d.len_band' % P, fl is not None and P * 65536 <= fl <= P * 65600 + 512, 'len_med=%s' % fl)
    check('n2.P%d.cap_band' % P, all(x[0] <= x[1] <= 2 * x[0] + 65664 for x in n['full']) and bool(n['full']), 'cap_med=%s' % fc)
    check('n3.P%d.read_alloc' % P, med(n['ra']) is not None and med(n['ra']) >= 2 * P * 65536, 'med=%s' % med(n['ra']))
lr = med([x[0] for x in R[('N', 512)]['full']]) / med([x[0] for x in R[('N', 128)]['full']])
check('n2.len_ratio', 3.9 <= lr <= 4.1, 'ratio=%.3f' % lr)
dN = {P: R[('N', P)]['dB'] for P in (128, 512)}
check('n4.grows_3x', dN[512] is not None and dN[128] is not None and dN[512] >= 3 * dN[128], 'dN=%s' % dN)
check('n4.ge_400', dN[512] is not None and dN[512] >= 400, 'dN512=%s' % dN[512])
check('n4.humongous_ge_64', R[('N', 512)]['dH'] is not None and R[('N', 512)]['dH'] >= 64, 'H512=%s' % R[('N', 512)]['dH'])
check('rowNC.floor_100_and_grows', dN[512] is not None and dN[512] >= 100 and dN[512] > dN[128], 'dN=%s' % dN)

for P in (128, 512):
    c = R[('C', P)]
    check('c1.P%d.all_refused' % P, refused_all(c), 'ok=%d err=%d classes=%s' % (c['ok'], len(c['err']), sorted(set((e.get('cls'), e.get('codes')) for e in c['err']))))
    check('c1.P%d.meter' % P, abs(c['dca'] - len(c['err'])) <= 16 and c['dla'] == 0, 'dca=%d refused=%d dla=%d' % (c['dca'], len(c['err']), c['dla']))
    check('c2.P%d.guard_size' % P, bool(c['gf']) and set(c['gf']) == {(16 * S, 1048576)}, 'set=%s n=%d' % (sorted(set(c['gf']))[:3], len(c['gf'])))
    check('c2.P%d.cmax' % P, c['cmax'] == bucket(16 * S), 'cmax=%d' % c['cmax'])
    fl = med([x[0] for x in c['full']]); nl = med([x[0] for x in R[('N', P)]['full']])
    check('c3.P%d.len_as_N' % P, fl is not None and abs(fl - nl) <= 0.01 * nl and P * 65536 <= fl <= P * 65600 + 512, 'C=%s N=%s' % (fl, nl))
    check('c3.P%d.read_alloc' % P, med(c['ra']) is not None and med(c['ra']) >= 2 * P * 65536, 'med=%s' % med(c['ra']))
    check('c4.P%d.ge_40pct_N' % P, c['dB'] is not None and dN[P] is not None and c['dB'] >= 0.4 * dN[P], 'dC=%s dN=%s' % (c['dB'], dN[P]))
check('c4.grows_2x', R[('C', 512)]['dB'] is not None and R[('C', 128)]['dB'] is not None and R[('C', 512)]['dB'] >= 2 * R[('C', 128)]['dB'],
      'dC=%s/%s' % (R[('C', 128)]['dB'], R[('C', 512)]['dB']))

for arm, T, k, lmaxp in (('L', MIB, 16, 1131752), ('L4', 4 * MIB, 64, 4866323)):
    for P in (128, 512):
        r = R[(arm, P)]
        tag = 'l' if arm == 'L' else 'L4-'
        check('%s1.%s.P%d.all_refused' % (tag, arm, P), refused_all(r), 'ok=%d err=%d' % (r['ok'], len(r['err'])))
        check('%s1.%s.P%d.meter' % (tag, arm, P), abs(r['dla'] - len(r['err'])) <= 16 and r['dca'] == 0, 'dla=%d refused=%d dca=%d' % (r['dla'], len(r['err']), r['dca']))
        X = b0 + k * h
        check('%s2.%s.P%d.X' % (tag, arm, P), bool(r['la']) and set(r['la']) == {X} and T <= X < T + h, 'set=%s pred=%d' % (sorted(set(r['la']))[:3], X))
        check('%s2.%s.P%d.lmax' % (tag, arm, P), r['lmax'] == lmaxp == bucket(X), 'lmax=%d' % r['lmax'])
        check('%s3.%s.P%d.no_full_page' % (tag, arm, P), len(r['full']) == 0, 'full=%d' % len(r['full']))
        check('%s3.%s.P%d.read_alloc_bound' % (tag, arm, P), med(r['ra']) is not None and med(r['ra']) < 5 * T + MIB, 'med=%s' % med(r['ra']))
    rr = med(R[(arm, 512)]['ra']) / med(R[(arm, 128)]['ra'])
    check('%s.alloc_not_grow_P' % arm, 0.8 <= rr <= 1.25, 'ratio=%.3f' % rr)
for P in (128, 512):
    l = R[('L', P)]
    check('l4.P%d.le_64' % P, l['dB'] is not None and l['dB'] <= 64, 'dL=%s' % l['dB'])
    check('l4.P%d.humongous_le_16' % P, l['dH'] is not None and l['dH'] <= 16, 'HL=%s' % l['dH'])
    check('L4-2.P%d.alloc_gt_L' % P, med(R[('L4', P)]['ra']) > med(l['ra']), 'L4=%s L=%s' % (med(R[('L4', P)]['ra']), med(l['ra'])))
    check('L4-3.P%d.le_128_ge_L' % P, R[('L4', P)]['dB'] is not None and R[('L4', P)]['dB'] <= 128 and R[('L4', P)]['dB'] >= l['dB'],
          'dL4=%s dL=%s' % (R[('L4', P)]['dB'], l['dB']))
check('l4.not_grow', R[('L', 512)]['dB'] <= R[('L', 128)]['dB'] + 32, 'dL=%s/%s' % (R[('L', 128)]['dB'], R[('L', 512)]['dB']))

# Z
cmd = open(os.path.join(CL, 'commands.log'), errors='replace').read()
zout = ''
for f in ('node.out', 'system.log'):
    p = os.path.join(CL, 'Z', f)
    if os.path.exists(p):
        zout += open(p, errors='replace').read()
check('Z.no_startup', 'Startup complete' not in zout, '')
check('Z.message', 'coordinator_read_size_fail_threshold (1MiB) must be greater than or equal to coordinator_read_size_warn_threshold (2MiB)' in zout, '')
print('SUMMARY %d of %d checks hold' % (sum(res), len(res)))
