#!/usr/bin/env python3
"""Independent self-check of run 1, CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT (stage 4, long path, 2026-10-14).

Re-parses the raw files only and re-applies the frozen 9a predictions (section 9 hash 71a37be9...):
  unit:    the test's STAGE4 note lines (<L>.out: T, slot class, copy length, delta, wire length) -- not its own check verdicts --
           and the upstream test's JUnit XML;
  cluster: per value, the Byteman traces (trace-p1.txt, trace-p2.txt), the hold files, the raw `jcmd GC.class_histogram`
           outputs (histo-p<n>-<label>.txt, parsed here, not histo.csv), the writers' client lines (writers-p1.txt), the
           JVM command lines (jvm-args.p<n>.txt) and the copied system logs.
It never reads summary.txt, histo.csv or sizes.json, the run script's own figures. Prints one line per check and a final count;
exit 1 on a failure.

usage: selfcheck.py [logroot]      (default ~/stage4-logs/cms)
"""
import glob, json, os, re, sys
import xml.etree.ElementTree as ET

ROOT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/stage4-logs/cms')
VALUES = [4000000, 1000000, 100000, 1, 0]
SIZES = [(100, 8, 90000), (108, 8, 500000), (116, 8, 2000000)]
SLACK = 65536

results = []


def chk(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(f'{"ok  " if cond else "FAIL"} {name}' + (f'  [{detail}]' if detail else ''))
    return bool(cond)


def info(s):
    print(f'     {s}')


def read(p):
    with open(p, errors='replace') as f:
        return f.read()


# ------------------------------------------------------------------ unit tier

def unit():
    print('== unit tier')
    x = f'{ROOT}/unit/TEST-org.apache.cassandra.utils.TeeDataInputPlusTest.xml'
    if chk('unit upstream XML present', os.path.exists(x), x):
        s = ET.parse(x).getroot()
        chk('unit upstream TeeDataInputPlusTest green', s.get('failures') == '0' and s.get('errors') == '0' and int(s.get('tests')) >= 1,
            f'tests={s.get("tests")} failures={s.get("failures")} errors={s.get("errors")}')
    for L in VALUES:
        f = f'{ROOT}/unit/{L}.out'
        if not chk(f'unit L={L} output present', os.path.exists(f), f):
            continue
        txt = read(f)
        notes = dict(re.findall(r'^STAGE4 note (\S+) (.*)$', txt, re.M))
        setup = re.search(r'^STAGE4 setup L=(-?\d+) current_version=(\d+) ordinal=(\d+)', txt, re.M)
        chk(f'unit L={L} setup line, L as set', setup and int(setup.group(1)) == L, setup.group(0) if setup else 'none')
        info(f'current_version={setup.group(2) if setup else "?"} ordinal={setup.group(3) if setup else "?"}')
        rb = dict(re.findall(r'^STAGE4 check (readback\.\w+) \S+ (\S+) ', txt, re.M))
        chk(f'unit L={L} read-back field and property = L', rb.get('readback.field') == str(L) and rb.get('readback.property') == str(L), str(rb))
        sup = re.search(r'^STAGE4 check setup.allocated_bytes_supported \S+ (\S+)', txt, re.M)
        chk(f'unit L={L} isThreadAllocatedMemorySupported', sup and sup.group(1) == 'true')
        ser, rec = {}, {}
        for n, body in notes.items():
            m = re.match(r'ser\.(\S+)$', n)
            if m:
                g = re.search(r'payload=(\d+) T=(\d+) slot=(\S+) delta=(-?\d+) scratch (\d+)->(\d+)', body)
                ser[m.group(1)] = {'p': int(g.group(1)), 'T': int(g.group(2)), 'slot': g.group(3), 'delta': int(g.group(4)),
                                   'c0': int(g.group(5)), 'c1': int(g.group(6))}
            m = re.match(r'recv\.(\S+)$', n)
            if m:
                g = re.search(r'payload=(\d+) W=(\d+) slot=(\S+)(?: copy=(\d+))?', body)
                rec[m.group(1)] = {'p': int(g.group(1)), 'W': int(g.group(2)), 'slot': g.group(3),
                                   'copy': int(g.group(4)) if g.group(4) else None}
        want_names = ['1024', 'p*', 'p*+1', '1.01L', '2L'] if L >= 100000 else ['1024', '100000', '3000000']
        chk(f'unit L={L} all sizes probed at both sites', all(n in ser and n in rec for n in want_names), f'{sorted(ser)} / {sorted(rec)}')
        # calibration (L >= 100,000): T(p*) = L - 1, T(p*+1) = L
        if L >= 100000 and 'p*' in ser and 'p*+1' in ser:
            chk(f'unit L={L} calibration T(p*) = L - 1 and T(p*+1) = L', ser['p*']['T'] == L - 1 and ser['p*+1']['T'] == L,
                f'T(p*)={ser["p*"]["T"]} T(p*+1)={ser["p*+1"]["T"]} p*={ser["p*"]["p"]}')
            chk(f'unit L={L} p*+1 is p* + 1', ser['p*+1']['p'] == ser['p*']['p'] + 1)
        # serialize site: a copy iff T < L (never for L <= 0), of length T -- re-derived from the note lines
        for n in want_names:
            s = ser.get(n)
            if not s:
                continue
            cached = s['T'] < L
            chk(f'unit L={L} ser {n}: slot {s["slot"]} (T={s["T"]}) as T<L predicts',
                s['slot'] == ('CachedSerialization' if cached else 'SizeOnlyCacheableSerialization'))
        lens = re.findall(r'^STAGE4 check ser\.(\S+)\.length (\d+) (-?\d+) ', txt, re.M)
        for n, exp, act in lens:
            chk(f'unit L={L} ser {n}: copy length {act} = T {ser[n]["T"]}', int(act) == ser[n]['T'])
        if L >= 100000 and 'p*' in ser and 'p*+1' in ser:
            d = ser['p*']['delta'] - ser['p*+1']['delta']
            T = ser['p*']['T']
            chk(f'unit L={L} heap: delta(p*) - delta(p*+1) = {d} in [T, T + 64 KiB] = [{T}, {T + SLACK}]', T <= d <= T + SLACK)
            c1 = ser['p*']['c1']
            info(f'scratch after p*: {c1} (recorded: >= T and <= 1 MiB, or 128) -> '
                 f'{"as predicted" if (T <= c1 <= 1048576) or c1 == 128 else "differs"}; '
                 f'p*+1: {ser["p*+1"]["c0"]} -> {ser["p*+1"]["c1"]} ({"unchanged" if ser["p*+1"]["c0"] == ser["p*+1"]["c1"] else "changed"})')
        # receive site: W = T of the same payload; a copy iff L <= 0 or W < L, of length W
        for n in want_names:
            r, s = rec.get(n), ser.get(n)
            if not (r and s):
                continue
            chk(f'unit L={L} recv {n}: W {r["W"]} = T {s["T"]}', r['W'] == s['T'])
            cached = L <= 0 or r['W'] < L
            chk(f'unit L={L} recv {n}: slot {r["slot"]} (W={r["W"]}) as predicted ({"copy" if cached else "null"})',
                r['slot'] == ('CachedSerialization' if cached else 'null') and (not cached or r['copy'] == r['W']))
        eq = re.findall(r'^STAGE4 check recv\.(\S+)\.bytes_equal_wire \S+ (\S+) ', txt, re.M)
        if eq:
            chk(f'unit L={L} recv copies equal the wire bytes ({len(eq)})', all(v == 'true' for _, v in eq))
        aft = re.findall(r'^STAGE4 check recv\.(\S+)\.after_size\.class (\S+) (\S+) ', txt, re.M)
        chk(f'unit L={L} recv slot after serializedSize as predicted ({len(aft)})', aft and all(e == a for _, e, a in aft), str(aft))
        tee = dict((k, v) for k, v in re.findall(r'^STAGE4 check (tee\.\S+) \S+ (\S+) ', txt, re.M))
        info(f'tee: {tee}')
        if L > 1:
            chk(f'unit L={L} tee L-1: not reached, L-1 mirrored', tee.get('tee.L-1.limit_reached') == 'false' and tee.get('tee.L-1.mirrored') == str(L - 1))
        if L >= 1:
            chk(f'unit L={L} tee L: reached, 0 mirrored', tee.get('tee.L.limit_reached') == 'true' and tee.get('tee.L.mirrored') == '0')
        if L == 0:
            chk(f'unit L=0 tee 3,000,000: not reached, all mirrored', tee.get('tee.0.limit_reached') == 'false' and tee.get('tee.0.mirrored') == '3000000')
        idle = re.search(r'^STAGE4 note idle meter=(-?\d+) delta=(-?\d+) scratch (\d+)->(\d+)', txt, re.M)
        chk(f'unit L={L} idle: allocation = the meter\'s own, scratch unchanged', idle and idle.group(1) == idle.group(2) and idle.group(3) == idle.group(4),
            idle.group(0) if idle else 'none')
        done = re.search(r'^STAGE4 done L=\S+ checks=(\d+) mismatches=(\d+)', txt, re.M)
        info(f'the test\'s own count: {done.group(0) if done else "no done line"}')


# ------------------------------------------------------------------ cluster tier

HIST_CLASSES = {'[B': 'B', 'org.apache.cassandra.db.Mutation$CachedSerialization': 'cached',
                'org.apache.cassandra.db.Mutation$SizeOnlyCacheableSerialization': 'sizeonly'}


def histo(path):
    if not os.path.exists(path):
        return None
    out = {'B_inst': 0, 'B_bytes': 0, 'cached_inst': 0, 'cached_bytes': 0, 'sizeonly_inst': 0, 'sizeonly_bytes': 0}
    rows = 0
    for l in open(path, errors='replace'):
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if not m:
            continue
        rows += 1
        k = HIST_CLASSES.get(m.group(3))
        if k:
            out[k + '_inst'] += int(m.group(1)); out[k + '_bytes'] += int(m.group(2))
    return out if rows > 10 else None


def trace(path, kind):
    rx = {'ser': re.compile(r'serialize T=(\d+) cached=(\w+) ks=(\w+) pk=(-?\d+) v=(\d+) '),
          'des': re.compile(r'deserialize cached=(true|false) teeLen=(\d+) ks=(\w+) pk=(-?\d+) v=(\d+) ')}[kind]
    out = []
    if os.path.exists(path):
        for l in open(path, errors='replace'):
            m = rx.match(l.strip())
            if m:
                out.append(m.groups())
    return out


def held(path):
    if not os.path.exists(path):
        return []
    return re.findall(r'^held ks=ks1 pk=(-?\d+) delay=(\d+) thread=.* ms=(\d+)$', read(path), re.M)


def cluster_value(L, H):
    D = f'{ROOT}/{L}'
    print(f'== cluster L={L}')
    if not chk(f'L={L} run folder present', os.path.isdir(D), D):
        return None
    for p in (1, 2):
        a = f'{D}/jvm-args.p{p}.txt'
        args = read(a).split('\n') if os.path.exists(a) else []
        chk(f'L={L} p{p} JVM has -Dcassandra.cacheable_mutation_size_limit_bytes={L}, -Xmx4G and Byteman',
            f'-Dcassandra.cacheable_mutation_size_limit_bytes={L}' in args and '-Xmx4G' in args and any('byteman-4.0.20.jar' in x for x in args))
    y = f'{D}/cassandra.p1.yaml'
    if os.path.exists(y):
        yt = read(y)
        chk(f'L={L} yaml: batch sync, no period, write timeout 120000ms, native_transport_timeout 180000ms',
            re.search(r'^commitlog_sync: batch$', yt, re.M) and not re.search(r'^commitlog_sync_period:', yt, re.M)
            and re.search(r'^write_request_timeout: 120000ms$', yt, re.M) and re.search(r'^native_transport_timeout: 180000ms$', yt, re.M))
    sess = read(f'{D}/session.log') if os.path.exists(f'{D}/session.log') else ''
    m = re.search(r'cassandra\.cacheable_mutation_size_limit_bytes=(\S+)', sess)
    chk(f'L={L} jcmd VM.system_properties reads back {L}', m and m.group(1) == str(L), m.group(0) if m else 'none')
    # Phase 1
    h1 = held(f'{D}/hold-p1.txt')
    chk(f'L={L} p1 24 held lines (ks1), pks 100..123', len(h1) == 24 and sorted(int(x[0]) for x in h1) == list(range(100, 124)), f'{len(h1)}')
    ser = trace(f'{D}/trace-p1.txt', 'ser')
    s1 = [x for x in ser if x[2] == 'ks1']
    c0 = [x for x in ser if x[2] == 'ks0']
    byp = {int(x[3]): x for x in s1}
    Ts = []
    for first, n, size in SIZES:
        tset = sorted({int(byp[p][0]) for p in range(first, first + n) if p in byp})
        Ts.append(tset[0] if len(tset) == 1 else None)
    chk(f'L={L} p1 24 serialize lines (ks1), one T per size', len(s1) == 24 and None not in Ts, f'{len(s1)} lines, T {Ts}')
    if None in Ts:
        return None
    if H is not None:
        chk(f'L={L} T per size equal to the first value\'s ({H})', Ts == H, str(Ts))
    c = sum(1 for t in Ts if t < L)
    wrong = [x for x in s1 if (x[1] == 'CachedSerialization') != (int(x[0]) < L)]
    chk(f'L={L} p1 every serialize line: cached=CachedSerialization iff T < L (c = {c})', not wrong, f'{len(wrong)} wrong')
    chk(f'L={L} p1 control (ks0): one line, T just above 1,024, branch as T<L predicts',
        len(c0) == 1 and 1024 < int(c0[0][0]) < 1200 and (c0[0][1] == 'CachedSerialization') == (int(c0[0][0]) < L), str(c0))
    cachedT = [t for t in Ts if t < L]
    if cachedT:
        chk(f'L={L} largest cached T {max(cachedT)} < L', max(cachedT) < L)
    hist = {lab: histo(f'{D}/histo-p1-{lab}.txt') for lab in ('idle-1', 'idle-2', 'held-1', 'held-2', 'release')}
    chk(f'L={L} p1 five histograms parsed', all(hist.values()), str([k for k, v in hist.items() if not v]))
    if not all(hist.values()):
        return None
    i1, i2 = hist['idle-1'], hist['idle-2']
    info(f'p1 idle: cached {i1["cached_inst"]}/{i2["cached_inst"]} sizeonly {i1["sizeonly_inst"]}/{i2["sizeonly_inst"]} '
         f'[B {i1["B_bytes"]}/{i2["B_bytes"]}')

    def between(v, key, pred):
        a, b = v[key] - i1[key], v[key] - i2[key]
        return min(a, b) <= pred <= max(a, b), (a, b)

    for lab in ('held-1', 'held-2'):
        okc, dc = between(hist[lab], 'cached_inst', 8 * c)
        oks, ds = between(hist[lab], 'sizeonly_inst', 8 * (3 - c))
        chk(f'L={L} p1 {lab}: CachedSerialization +{dc} vs +{8 * c}, SizeOnly +{ds} vs +{8 * (3 - c)}', okc and oks)
    okr1, dr1 = between(hist['release'], 'cached_inst', 0)
    okr2, dr2 = between(hist['release'], 'sizeonly_inst', 0)
    chk(f'L={L} p1 release back to the idle baseline (cached {dr1}, sizeonly {dr2})', okr1 and okr2)
    # writers: all 24 OK, after the hold
    wt = read(f'{D}/writers-p1.txt') if os.path.exists(f'{D}/writers-p1.txt') else ''
    res = []
    for l in wt.splitlines():
        if l.startswith('OK ') or l.startswith('ERR '):
            body = json.loads(l.split(' ', 2)[2] if l.startswith('ERR ') else l[3:])
            res += body.get('results', [])
    oks = [r for r in res if r.get('ok')]
    secs = [r['secs'] for r in res]
    chk(f'L={L} p1 writers: 24 of 24 OK', len(res) == 24 and len(oks) == 24, f'{len(oks)}/{len(res)}; secs {min(secs) if secs else None}..{max(secs) if secs else None}')
    # Phase 2
    h2 = held(f'{D}/hold-p2.txt')
    chk(f'L={L} p2 24 held lines (ks1)', len(h2) == 24, f'{len(h2)}')
    des = trace(f'{D}/trace-p2.txt', 'des')
    d1 = {int(x[3]): x for x in des if x[2] == 'ks1'}
    dctl = [x for x in des if x[2] == 'ks0']
    chk(f'L={L} p2 24 deserialize lines (ks1)', len(d1) == 24 and len([x for x in des if x[2] == 'ks1']) == 24)
    cprime = c if L >= 1 else 3
    wrong = []
    for (first, n, size), t in zip(SIZES, Ts):
        want = L <= 0 or t < L
        for p in range(first, first + n):
            x = d1.get(p)
            if x is None or (x[0] == 'true') != want or (want and int(x[1]) != t) or (not want and int(x[1]) >= L):
                wrong.append(p)
    chk(f'L={L} p2 deserialize: cached=true with teeLen = T on {8 * cprime}, cached=false with teeLen < L on the rest', not wrong, f'wrong {wrong}')
    info(f'p2 control (ks0, recorded): {dctl}')
    hist2 = {lab: histo(f'{D}/histo-p2-{lab}.txt') for lab in ('held-1', 'held-2', 'release')}
    chk(f'L={L} p2 three histograms parsed', all(hist2.values()))
    if all(hist2.values()):
        tol = abs(i1['cached_inst'] - i2['cached_inst'])
        for lab in ('held-1', 'held-2'):
            dc = hist2[lab]['cached_inst'] - hist2['release']['cached_inst']
            ds = hist2[lab]['sizeonly_inst'] - hist2['release']['sizeonly_inst']
            chk(f'L={L} p2 {lab}: CachedSerialization held - after = {dc} vs +{8 * cprime} (tol {tol})', abs(dc - 8 * cprime) <= tol)
            info(f'p2 {lab}: SizeOnly held - after = {ds} (recorded; predicted 0)')
        okr1, dr1 = between(hist2['release'], 'cached_inst', 0)
        okr2, dr2 = between(hist2['release'], 'sizeonly_inst', 0)
        chk(f'L={L} p2 release vs p1 idle pair (cached {dr1}, sizeonly {dr2})', okr1 and okr2)
    syslogs = ''.join(read(f) for f in sorted(glob.glob(f'{D}/system.*.log')))
    rp = re.search(r'Log replay complete, (\d+) replayed mutations', syslogs)
    chk(f'L={L} replay ran: "Replaying ...CommitLog-" and "Log replay complete" in the system log', re.search(r'Replaying .*CommitLog-', syslogs) and rp,
        rp.group(0) if rp else 'none')
    chk(f'L={L} no ERROR line in the system logs', not re.search(r'^ERROR ', syslogs, re.M))
    chk(f'L={L} no write timeout / failure logged for ks1', not re.search(r'WriteTimeoutException|Failed to apply mutation locally', syslogs))
    return {'T': Ts, 'c': c, 'p1': hist, 'p2': hist2}


def cross(data):
    print('== cluster across values')
    Ts = next((d['T'] for d in data.values() if d), None)
    if not Ts:
        chk('cross: sizes known', False); return
    for lab in ('held-1', 'held-2'):
        if not (data.get(0) and data.get(1)):
            chk(f'cross {lab}: L=0 and L=1 runs present', False); continue
        SB = abs(data[0]['p1'][lab]['B_bytes'] - data[1]['p1'][lab]['B_bytes'])
        info(f'{lab}: S_B = {SB} B (3 S_B = {3 * SB})')
        exc = {}
        for v in (100000, 1000000, 4000000):
            if not data.get(v):
                continue
            pred = 8 * sum(((t + 16 + 7) // 8) * 8 for t in Ts if t < v)
            for ph in ('p1', 'p2'):
                e = data[v][ph][lab]['B_bytes'] - data[1][ph][lab]['B_bytes']
                exc[(v, ph)] = e
                tol = max(0.10 * pred, 3 * SB)
                if pred > 3 * SB:
                    chk(f'cross {lab} {ph} L={v}: [B excess {e} vs {pred} (tol {tol:.0f})', abs(e - pred) <= tol)
                else:
                    info(f'{lab} {ph} L={v}: [B excess {e} vs {pred}: below 3 S_B, recorded, not read')
        for ph in ('p1', 'p2'):
            if (4000000, ph) in exc and (1000000, ph) in exc and exc[(1000000, ph)]:
                info(f'{lab} {ph}: dose-response {exc[(4000000, ph)] / exc[(1000000, ph)]:.2f} (about 4.4 predicted)')
        if data.get(0):
            e0 = data[0]['p2'][lab]['B_bytes'] - data[1]['p2'][lab]['B_bytes']
            pred0 = 8 * sum(((t + 16 + 7) // 8) * 8 for t in Ts)
            if pred0 > 3 * SB:
                chk(f'cross {lab} p2 L=0 (scenario C): [B excess {e0} vs {pred0} (all three sizes)', abs(e0 - pred0) <= max(0.1 * pred0, 3 * SB))
    flat = len({(d['c'], d['p1']['held-1']['cached_inst'] - d['p1']['idle-1']['cached_inst']) for d in data.values() if d}) == 1
    chk('cross: counts are not the same at every value (not flat)', not flat)


unit()
data, H = {}, None
for v in VALUES:
    data[v] = cluster_value(v, H)
    if data[v] and H is None:
        H = data[v]['T']
cross(data)
fails = [n for n, ok in results if not ok]
print(f'\n{len(results)} checks, {len(fails)} failed')
for n in fails:
    print('  FAILED: ' + n)
sys.exit(1 if fails else 0)
