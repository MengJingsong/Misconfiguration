#!/usr/bin/env python3
"""Independent self-check for initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous. usage: python3 -I selfcheck.py <run>
Re-parses the raw files of ~/s4-b7-ie-logs/<run>/ (unit: x128.out x1g.out x4g.out; cluster: per arm ec.trace, histo-*.txt, jfr.json, system.log,
summary.txt client lines, phases.json for the data-dir bytes) without using the run scripts' own arithmetic: the allocation arithmetic is
re-derived here in closed form (sum of 2^k blocks), not by the probe's loop. Prints SC lines, `holds` / `DOES NOT HOLD`, and the cross-arm tables."""
import json, os, re, sys

RUN = sys.argv[1]
L = os.path.expanduser(f'~/s4-b7-ie-logs/{RUN}')
bad = 0


def sc(name, ok, detail=''):
    global bad
    if not ok:
        bad += 1
    print(f'SC {name}: {"holds" if ok else "DOES NOT HOLD"} {detail}')


def a8(x):
    return -(-x // 8) * 8


def closed_form(n, init):
    """bytes allocated by readBytes(n bytes, initial capacity init), in closed form from the code's behaviour:
    the buffer length goes init, 2 init, ... until it holds n (doubling only when a byte arrives at a full buffer),
    then one exact copy if n differs from the final length"""
    k = 0
    while init * (1 << k) < n:
        k += 1
    final = init * (1 << k)
    tot = sum(a8(16 + init * (1 << j)) for j in range(k + 1))
    if n != final:
        tot += a8(16 + n)
    return tot


# ---------------- unit tier
print('== unit tier')
meas = {}
for tag in ('x128', 'x1g', 'x4g'):
    f = f'{L}/unit/{tag}.out'
    if not os.path.exists(f):
        sc(f'unit file {tag}', False, 'missing')
        continue
    for l in open(f):
        if l.startswith('STAGE4 m ') and ' retained ' not in l and 'path=' not in l:
            kv = dict(x.split('=', 1) for x in l.split()[3:] if '=' in x)
            meas[(tag, int(kv['n']), int(kv['init']))] = kv
    chk = [l for l in open(f) if l.startswith('STAGE4 check')]
    sc(f'unit {tag} check lines all ok', all(' ok ' in l for l in chk), f'{len(chk)} checks')
rows = [(k, v) for k, v in meas.items() if k[0] != 'x4g']
dev = []
for (tag, n, init), kv in rows:
    allv = sorted(int(x) for x in kv['all'].strip('[]').split(','))
    med = allv[len(allv) // 2]
    exp = closed_form(n, init)
    if abs(med - exp) > max(256, 0.01 * exp):
        dev.append((tag, n, init, med, exp))
    if int(kv['len']) != n or kv['exc'] != 'null':
        dev.append((tag, n, init, 'len/exc', kv['len'], kv['exc']))
sc('unit: median allocation = closed-form sum for every (heap, N, initial) point; result length N; no exception', not dev, f'{len(rows)} points; deviations {dev[:5]}')
ratios = {n: float(kv['ratio']) for (tag, n, init), kv in meas.items() if tag == 'x1g' and init == 32 and n >= 1000}
sc('unit: ratio 2.0 for powers of two, about 3.0 for 65535', abs(ratios[1 << 20] - 2.0) < 0.01 and abs(ratios[64 << 20] - 2.0) < 0.01 and abs(ratios[65535] - 3.0) < 0.02, str(ratios))
pairs = [(k[1], k[2]) for k in meas if k[0] == 'x128']
same = all(meas[('x128', n, i)]['alloc'] == meas[('x1g', n, i)]['alloc'] for (n, i) in pairs if ('x1g', n, i) in meas)
sc('unit: allocation equal at -Xmx128m and -Xmx1g', same, f'{len(pairs)} points')
big = {k[1]: v for k, v in meas.items() if k[0] == 'x4g'}
sc('unit: N = 1<<30 returns 1<<30 bytes; N = (1<<30)+1 throws NegativeArraySizeException',
   big.get(1 << 30, {}).get('len') == str(1 << 30) and big.get((1 << 30) + 1, {}).get('exc') == 'java.lang.NegativeArraySizeException',
   str({k: (v.get('len'), v.get('exc')) for k, v in big.items()}))
ctl = [l for tag in ('x128', 'x1g') for l in open(f'{L}/unit/{tag}.out') if l.startswith('STAGE4 check control-copyBytes')]
sc('unit: positive control copyBytes throws exactly when N > M', len(ctl) == 24 and all(' ok ' in l for l in ctl), f'{len(ctl)} control checks')

# ---------------- cluster tier
print('== cluster tier')
K_OF = {'k16': 16, 'k1k': 1024, 'k32k': 32768, 'k64k': 65535, 'k16m': 16, 'k64km': 65535, 'k16n': 16, 'k64kn': 65535, 'ctl': 1024}
ROWS = {'k16': 20000, 'k1k': 20000, 'k32k': 2000, 'k64k': 2000, 'k16m': 20000, 'k64km': 2000, 'k16n': 20000, 'k64kn': 2000, 'ctl': 2000}
table = {}
for arm, K in K_OF.items():
    d = f'{L}/cluster/{arm}'
    if not os.path.exists(f'{d}/summary.txt'):
        print(f'-- {arm}: not run')
        continue
    calls = []
    exc = 0
    summ0 = open(f'{d}/summary.txt').read()
    if not os.path.exists(f'{d}/ec.trace'):
        # the helper creates the file at the first traced call: no file means no readBytes call in the lifetime, which is a reading only if the agent was loaded
        sc(f'{arm}: no ec.trace file = zero readBytes calls; the Byteman agent and the boot-class-path helper were on the JVM command line', 'javaagent' in summ0 and 'Xbootclasspath/a' in summ0 and 'node stopped' in summ0)
    for l in (open(f'{d}/ec.trace') if os.path.exists(f'{d}/ec.trace') else []):
        if l.startswith('rbexc'):
            exc += 1
        elif l.startswith('rb '):
            kv = dict(x.split('=', 1) for x in l.split()[1:] if '=' in x)
            calls.append((re.sub(r':\d+$', '', kv['caller']), int(kv['bytes']), int(kv['len'])))
    sm = [c for c in calls if c[0] == 'SegmentMetadata.write']
    pk = [c for c in calls if c[0].startswith('PrimaryKey$Factory.partitionKeyFromComparableBytes')]
    other = {}
    for c in calls:
        other[c[0]] = other.get(c[0], 0) + 1
    under = [c for c in calls if c[1] < closed_form(c[2], 32)]
    grow = [sum(a8(16 + 32 * (1 << j)) for j in range(1, max(0, (c[2] - 1).bit_length() - 5) + 1)) for c in calls]  # arrays created by ensureCapacity
    big_calls = [(g, c) for g, c in zip(grow, calls) if c[2] >= 1000]
    worst = max((g / c[2] for g, c in big_calls), default=0)
    maxlen = max((c[2] for c in calls), default=0)
    histo = {}
    for tag in ('base', 'final'):
        t = open(f'{d}/histo-{tag}.txt').read()
        m = re.search(r'^Total\s+(\d+)\s+(\d+)', t, re.M)
        histo[tag] = int(m.group(2)) if m else None
    jfr = json.load(open(f'{d}/jfr.json')) if os.path.exists(f'{d}/jfr.json') else {}
    ph = json.load(open(f'{d}/phases.json'))
    nerr = sum(1 for l in open(f'{d}/system.log', errors='replace') if l.startswith('ERROR') and 'Guardrail sai_string_term_size violated' not in l)   # arm ctl logs each rejected write at ERROR (NoSpamLogger): the control itself
    summ = open(f'{d}/summary.txt').read()
    errs = sum(json.loads(m.group(1)).get('err', 0) for m in re.finditer(r'^load[12]: (\{.*\})$', summ, re.M))
    loads = [json.loads(m.group(1)) for m in re.finditer(r'^load[12]: (\{.*\})$', summ, re.M)]
    q = re.search(r'^queries: (\{.*\})$', summ, re.M)
    q = json.loads(q.group(1)) if q else {}
    big_ins = re.search(r'^big \(4 KiB v\) inserts: (\{.*\})$', summ, re.M)
    table[arm] = dict(K=K, rows=ROWS[arm], n_sm=len(sm), sm_maxlen=max((c[2] for c in sm), default=0), n_pk=len(pk), pk_maxlen=max((c[2] for c in pk), default=0),
                      maxlen=maxlen, exc=exc, under=len(under), worst_grow_per_len=worst, grow_max=max(grow, default=0), bytes_max=max((c[1] for c in calls), default=0),
                      histo_delta=(histo['final'] - histo['base']) if histo['base'] and histo['final'] else None, data=ph['final']['data_bytes'],
                      jfr_share=jfr.get('share_ensureCapacity'), jfr_events=jfr.get('events'), load_errs=errs, load_ok=sum(x.get('ok', 0) for x in loads), log_errors=nerr,
                      q_ok=q.get('ok'), q_err=q.get('err'), other=other, big=json.loads(big_ins.group(1)) if big_ins else None)
    t = table[arm]
    idx = not arm.endswith('n')
    sc(f'{arm}: no readBytes call threw; every call allocated at least the closed-form sum for its length', exc == 0 and not under, f'{len(calls)} calls, exc {exc}, under {len(under)}')
    if idx:
        sc(f'{arm}: SegmentMetadata.write decoded keys of about K bytes (K={K}): max_len in [K, 1.02K+64]', len(sm) >= 2 and K <= t['sm_maxlen'] <= 1.02 * K + 64, f'n={len(sm)} max_len={t["sm_maxlen"]}')
    else:
        sc(f'{arm}: no SAI index, so no readBytes call from SegmentMetadata.write', len(sm) == 0, f'callers {other}')
    sc(f'{arm}: closed-form ensureCapacity allocation per call <= 4.1 x len for len >= 1000, and <= 4 x 65535 B plus the 16-byte array headers (12 arrays: +192 B; the run script literal bound without headers is missed by 132 B)', worst <= 4.1 and t['grow_max'] <= 4 * 65535 + 200, f'worst {worst:.3f} max {t["grow_max"]}')
    sc(f'{arm}: no write failed, no ERROR line, all {ROWS[arm]} rows acknowledged', errs == 0 and nerr == 0 and t['load_ok'] == ROWS[arm], f'errs {errs} ERROR lines {nerr} ok {t["load_ok"]}')
    sc(f'{arm}: all {q.get("queries")} queries answered', q.get('err') == 0 and q.get('ok') == q.get('queries'), str(q))
    if arm == 'ctl':
        b = t['big']
        sc('ctl: the twenty 4 KiB-v inserts were all rejected at fail threshold 1 KiB', bool(b) and b.get('err') == 20 and b.get('ok') == 0, str(b))
print(json.dumps(table, indent=1))
# cross-arm relations
print('== cross-arm')
for h, (a, b_) in {'1g': ('k16', 'k64k'), '512m': ('k16m', 'k64km')}.items():
    if a in table and b_ in table:
        da, db = table[a]['histo_delta'], table[b_]['histo_delta']
        sc(f'retained live heap, K=65535 minus K=16 at {h}, under 16 MiB', abs(db - da) < 16 << 20, f'{a}={da} {b_}={db} diff={db - da}')
        ra, rb = table[a]['data'] / (table[a]['rows'] * (table[a]['K'] + 1000)), table[b_]['data'] / (table[b_]['rows'] * (table[b_]['K'] + 1000))
        print(f'   data dir bytes / raw input bytes ({h}): K=16 {ra:.3f}  K=65535 {rb:.3f}')
for arm, t in table.items():
    if t['jfr_share'] is not None:
        sc(f'{arm}: JFR allocation weight under ensureCapacity below 1 percent', t['jfr_share'] < 0.01, f'share {t["jfr_share"]:.5f} of {t["jfr_events"]} events')
ks = [(table[a]['K'], table[a]['sm_maxlen']) for a in ('k16', 'k1k', 'k32k', 'k64k') if a in table]
if len(ks) == 4:
    sc('decode size follows K across the four key sizes (max_len within [K, 1.02K+64])', all(k <= m <= 1.02 * k + 64 for k, m in ks), str(ks))
print(f'SELF-CHECK RESULT: {"all parts hold" if bad == 0 else str(bad) + " part(s) DO NOT HOLD"}')
