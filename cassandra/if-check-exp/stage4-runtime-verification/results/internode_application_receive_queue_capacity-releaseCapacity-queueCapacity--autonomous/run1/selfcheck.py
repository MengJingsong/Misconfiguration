#!/usr/bin/env python3
"""Self-check of run 1 (results §5) for internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--
autonomous. Independent of cluster-run.py's analysis: it re-reads the raw files and recomputes every figure the
conclusion uses, with its own parsing:
  unit     harness.out (every STAGE4 check line; the B2f values compared with the constants of B2f's text), the
           ant logs of the upstream test, the two harness classes and the three mutants
  cluster  per label: rrc.trace (whole file: data-handler peak q, M, refusals and their outcomes; the release rule of
           :464 recomputed per handler as sums, not by pairing lines), jmx-B.csv (ThrottledCount over the window that
           session.log's own timestamps give: stress launch to the drain note), samples/histo-*.txt (retained =
           Mutation + [B above idle, live Mutation count), threads-load1.txt (held workers), vt-in-after.csv (drained),
           B-system.log (OutOfMemoryError); then compares its figures with readings.json, and recomputes the cross-run
           relations of analyze (B3f/B3g/B3h).
usage: selfcheck.py <run root, e.g. ~/stage4-logs/rrc/run1>"""
import csv, glob, json, os, re, statistics, sys, time

root = os.path.expanduser(sys.argv[1])
KIB, MIB = 1024, 1 << 20
ok_all = True
nchk = {'ok': 0, 'bad': 0}


def chk(name, cond, detail=''):
    global ok_all
    nchk['ok' if cond else 'bad'] += 1
    ok_all &= bool(cond)
    print(f'{"ok  " if cond else "FAIL"} {name}: {detail}')


# ------------------------------------------------------------------ unit
U = root + '/unit'
lines = [l.strip() for l in open(U + '/harness.out')]
checks = [l for l in lines if l.startswith('STAGE4 check ')]
vals = {}
for l in checks:
    m = re.match(r'STAGE4 check (\S+) expected=(.*) actual=(.*) (ok|MISMATCH)$', l)
    vals[m.group(1)] = (m.group(2), m.group(3), m.group(4))
chk('unit: every check line ok', all(v[2] == 'ok' and v[0] == v[1] for v in vals.values()),
    f'{len(vals)} checks, {sum(1 for v in vals.values() if v[2] != "ok")} not ok, '
    f'{sum(1 for v in vals.values() if v[0] != v[1])} with expected != actual')
B2F = {  # B2f's stated values, typed in from the case file (not from the test source)
    'script.Q1024.R2048.sequence': '[600/0, 1200/176, 1200/176, 600/0, 0/0]',
    'script.Q1024.R2048.outcomes': '[SUCCESS, SUCCESS, INSUFFICIENT_GLOBAL]',
    'boundary.eq.rel.released': 'E=100 G=100',          # old == Q releases 0 (another handler holds 100)
    'boundary.plus1.rel.released1': 'E=100 G=100',      # old == Q+1, bytes 5: 101 -> 100, exactly 1 released
    'throttled.outer.count': '1', 'throttled.inner.count': '0',
    'script.Q4096.R2048.borrowsNothing': '0', 'script.Q4096.R8192.borrowsNothing': '0',
    'defaults.queueCapacity': '4194304', 'config.8MiB.queueCapacity': '8388608',
    **{f'concurrent.rep{i}.final': '(0,0,0)' for i in range(1, 6)},
    **{f'concurrent.rep{i}.errors': '[]' for i in range(1, 6)},
}
for k, want in B2F.items():
    got = vals.get(k, (None, None, None))[1]
    chk(f'unit B2f {k}', got == want, f'actual {got} vs B2f {want}')
# (fixed after the first self-check pass: 23 script steps = 5 + 6 + 6 + 6; x.react.retry.inv is not a script step)
inv = [k for k in vals if k.startswith('script.') and k.endswith('.inv')]
chk('unit B2f invariant E == G == max(0, q - Q) at every script step', len(inv) == 23 and all(vals[k][2] == 'ok' for k in inv),
    f'{len(inv)} steps')
wr = [k for k in vals if k.startswith('script.') and k.endswith('.withinR')]
chk('unit B2f never q - Q > R for an admitted state', all(vals[k][1] == 'true' for k in wr), f'{len(wr)} steps')
fin = [k for k in vals if k.startswith('script.') and k.endswith('.final')]
chk('unit B2f final state (0,0,0) for all four (Q, R)', len(fin) == 4 and all(vals[k][1] == '(0,0,0)' for k in fin), str(fin))


def antres(f):
    t = open(U + '/' + f, errors='replace').read()
    m = re.search(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+)', t)
    return tuple(int(x) for x in m.groups()) if m else None, ('BUILD SUCCESSFUL' in t)


for f, want_pass in (('upstream-ResourceLimitsTest.ant.log', True), ('probe.ant.log', True), ('config.ant.log', True),
                     ('mutant-M1.ant.log', False), ('mutant-M2.ant.log', False), ('mutant-M0.ant.log', True)):
    r, succ = antres(f)
    passed = succ and r is not None and r[1] == 0 and r[2] == 0
    chk(f'unit {f}: {"passes" if want_pass else "fails"}', passed == want_pass, f'tests/failures/errors {r}, build ok {succ}')
for m in ('M1', 'M2', 'M0'):
    d = open(f'{U}/mutant-{m}.diff').read()
    print(f'     mutant {m} diff: ' + ' | '.join(l for l in d.splitlines() if l.startswith(('+ ', '- ', '+\t', '-\t'))
                                                  or (l[:1] in '+-' and 'STAGE4' in l))[:300])
for m in ('M1', 'M2'):
    mm = [l for l in open(f'{U}/mutant-{m}.out') if 'MISMATCH' in l]
    print(f'     mutant {m}: {len(mm)} mismatching checks, e.g. {mm[0].strip()[:160] if mm else "-"}')

# ------------------------------------------------------------------ cluster
CL = root + '/cluster'
ID_RX = re.compile(r'^(/[\d.]+:\d+)->(/[\d.]+:\d+)-([A-Z_]+)-(\S+)$')
CFG = {'s1q64k': (64 * KIB, 16 * MIB), 's1q4m-1': (4 * MIB, 16 * MIB), 's1q4m-2': (4 * MIB, 16 * MIB),
       's1q4m-3': (4 * MIB, 16 * MIB), 's1q32m': (32 * MIB, 16 * MIB), 's2q64k': (64 * KIB, 128 * MIB),
       's2q4m': (4 * MIB, 128 * MIB), 's2q32m': (32 * MIB, 128 * MIB), 'ctla-q64k': (64 * KIB, 16 * MIB),
       'ctla-q32m': (32 * MIB, 16 * MIB), 'ctlb': (64 * KIB, 4 * MIB), 'ctlc': (4 * MIB, 16 * MIB)}
HELD = {l for l in CFG if not l.startswith('ctla')}
mine = {}


def hist(path):
    out = {}
    for l in open(path, errors='replace'):
        p = l.split()
        if len(p) >= 4 and p[0].endswith(':') and p[1].isdigit():
            out[p[3]] = (int(p[1]), int(p[2]))
    return out


def ts(s):  # session.log "[YYYY-mm-dd HH:MM:SS]" in the node's local time -> epoch ms
    return int(time.mktime(time.strptime(s, '%Y-%m-%d %H:%M:%S')) * 1000)


for lab, (Q, E) in CFG.items():
    D = f'{CL}/{lab}'
    if not os.path.exists(D + '/readings.json'):
        chk(f'{lab}: present', False, 'no readings.json')
        continue
    R = json.load(open(D + '/readings.json'))
    payload = 1024 if lab == 'ctlc' else 524288
    dtype = 'SMALL_MESSAGES' if lab == 'ctlc' else 'LARGE_MESSAGES'
    peak, bs, outs, nref, holds = 0, [], {}, 0, 0
    rel_exp, rel_cnt, relx_sum, relx_cnt, relx_bad_old = {}, {}, {}, {}, 0
    caps = {}
    for l in open(D + '/rrc.trace', errors='replace'):
        p = l.split()
        if not p:
            continue
        kv = dict(x.split('=', 1) for x in p[1:] if '=' in x)
        if p[0] == 'acq':
            m = ID_RX.match(kv['id'])
            if m and m.group(1) == '/127.0.0.2:7000' and m.group(3) == dtype:
                b = int(kv['b'])
                if b > payload:
                    bs.append(b)
                if kv['out'] == 'SUCCESS':
                    peak = max(peak, int(kv['q']))
                else:
                    nref += 1
                    outs[kv['out']] = outs.get(kv['out'], 0) + 1
        elif p[0] == 'rel':
            i, old, cap, b = kv['id'], int(kv['old']), int(kv['cap']), int(kv['b'])
            caps[i] = cap
            if old > cap:
                rel_exp[i] = rel_exp.get(i, 0) + min(old - cap, b)
                rel_cnt[i] = rel_cnt.get(i, 0) + 1
        elif p[0] == 'relx':
            i = kv['id']
            relx_sum[i] = relx_sum.get(i, 0) + int(kv['excess'])
            relx_cnt[i] = relx_cnt.get(i, 0) + 1
            if i in caps and int(kv['old']) <= caps[i]:
                relx_bad_old += 1
        elif p[0] == 'hold':
            holds += 1
    M = statistics.median(bs) if bs else None
    ids = set(rel_exp) | set(relx_sum)
    rule_ok = all(rel_exp.get(i, 0) == relx_sum.get(i, 0) and rel_cnt.get(i, 0) == relx_cnt.get(i, 0) for i in ids)
    chk(f'{lab}: line 464 per handler: sum of min(old - cap, b) over releases with old > cap = sum of released excess, '
        f'counts equal, no excess release at old <= cap', rule_ok and relx_bad_old == 0,
        f'{len(ids)} handlers, {sum(rel_cnt.values())} releases above cap, released {sum(relx_sum.values())} B')
    # window from session.log
    sl = open(D + '/session.log', errors='replace').read()
    m0 = re.search(r'^\[([\d-]+ [\d:]+)\] \+ tools/bin/cassandra-stress', sl, re.M)
    m1 = re.search(r'^\[([\d-]+ [\d:]+)\] drained: ', sl, re.M)
    w0, w1 = ts(m0.group(1)), ts(m1.group(1)) + 999
    jr = []
    for l in open(D + '/jmx-B.csv'):
        p = l.strip().split(',')
        if p and p[0].isdigit() and len(p) > 3 and p[1] not in ('ERR', ''):
            jr.append((int(p[0]), float(p[1]), float(p[3])))
    jw = [r for r in jr if w0 <= r[0] <= w1]
    thr = jw[-1][1] - jw[0][1] if len(jw) > 1 else None
    span = (jw[-1][0] - jw[0][0]) / 1000 if len(jw) > 1 else None
    rate = thr / span if thr is not None and span else None
    # histograms
    hi = hist(D + '/samples/histo-idle.txt')
    base = hi.get('org.apache.cassandra.db.Mutation', (0, 0))[1] + hi.get('[B', (0, 0))[1]
    rets, live = [], []
    for f in sorted(glob.glob(D + '/samples/histo-load*.txt'), key=lambda x: int(re.search(r'load(\d+)', x).group(1))):
        h = hist(f)
        rets.append(h.get('org.apache.cassandra.db.Mutation', (0, 0))[1] + h.get('[B', (0, 0))[1] - base)
        live.append(h.get('org.apache.cassandra.db.Mutation', (0, 0))[0] - hi.get('org.apache.cassandra.db.Mutation', (0, 0))[0])
    ha = hist(D + '/samples/histo-after.txt')
    mut_after = ha.get('org.apache.cassandra.db.Mutation', (0, 0))[0] - hi.get('org.apache.cassandra.db.Mutation', (0, 0))[0]
    retp = max(rets) if rets else None
    held = 0
    tf = D + '/samples/threads-load1.txt'
    if os.path.exists(tf):
        held = sum(1 for blk in open(tf, errors='replace').read().split('\n\n')
                   if 'MutationVerbHandler.doVerb' in blk and 'Thread.sleep' in blk)
    va = [r for r in csv.DictReader(open(D + '/vt-in-after.csv')) if r['address'] == '127.0.0.2']
    drained = bool(va) and va[-1]['using_bytes'] == '0' and va[-1]['using_reserve_bytes'] == '0' and mut_after <= 2
    blog = open(D + '/B-system.log', errors='replace').read()
    oom = blog.count('java.lang.OutOfMemoryError')
    C = Q + E
    mine[lab] = dict(Q=Q, E=E, C=C, M=M, peak=peak, nref=nref, outs=outs, thr=thr, rate=rate, retp=retp, rets=rets,
                     live=live, held=held, holds=holds, drained=drained, oom=oom)
    print(f'     {lab}: M {M}, peak q {peak} ({peak / M if M else 0:.3f} M), C {C}, refusals {nref} {outs}, ThrottledCount '
          f'delta {thr} over {span} s = {rate and round(rate, 2)}/s, retained {rets} peak {retp} '
          f'(k {retp / C if retp else 0:.3f}), live Mutation {live}, held workers {held}, hold lines {holds}, '
          f'drained {drained}, OOM {oom}')
    # agreement with the run script
    chk(f'{lab}: agrees with readings.json (M, peak q, refusals, retained peak)',
        M == R['M_med'] and peak == R['peak_q'] and nref == R['refusals'] and retp == R['retained_peak'],
        f'mine {M}/{peak}/{nref}/{retp} vs run {R["M_med"]}/{R["peak_q"]}/{R["refusals"]}/{R["retained_peak"]}')
    chk(f'{lab}: ThrottledCount delta agrees with readings.json within 1 % (window from session.log, 1 s grain)',
        thr is not None and R['throttled'] is not None and abs(thr - R['throttled']) <= max(2, 0.01 * R['throttled']),
        f'{thr} vs {R["throttled"]}')
    if lab in HELD:
        chk(f'{lab}: the hold fired', holds > 0 and held > 0, f'hold lines {holds}, held workers {held}')
    chk(f'{lab}: drained, live Mutation back to idle (+{mut_after}), no OOM', drained and oom == 0, '')
    if lab.startswith('s1') or lab == 'ctlb':
        chk(f'{lab}: B3f/R2 accounted ceiling: peak in (C - M, C]', M is not None and C - M < peak <= C,
            f'{peak} in ({C - (M or 0)}, {C}]')
        chk(f'{lab}: limit reached (B3g row 4 excluded): refusals > 0, ThrottledCount > 0', nref > 0 and (thr or 0) > 0,
            f'{nref}, {thr}')
    if lab.startswith('s1'):
        k = retp / C if retp is not None else None
        print(f'     {lab}: B3f k = retained / C = {k and round(k, 3)} (B3f band 1.2-3: {"in" if k and 1.2 <= k <= 3 else "OUT"})')

# cross-run (recomputed)
if all(l in mine for l in ('s1q4m-1', 's1q4m-2', 's1q4m-3', 's1q64k', 's1q32m')):
    reps = [mine[l] for l in ('s1q4m-1', 's1q4m-2', 's1q4m-3')]
    nret = max(r['retp'] for r in reps) - min(r['retp'] for r in reps)
    nrate = max(r['rate'] for r in reps) - min(r['rate'] for r in reps)
    nq = max(r['peak'] for r in reps) - min(r['peak'] for r in reps)
    a, b = mine['s1q64k'], mine['s1q32m']
    mret = statistics.mean(r['retp'] for r in reps)
    mrate = statistics.mean(r['rate'] for r in reps)
    print(f'     noise (range of 3 repeats): retained {nret}, rate {nrate:.3f}/s, peak q {nq}')
    print(f'     set 1 retained peak 64K / 4M (mean) / 32M: {a["retp"]} / {mret:.0f} / {b["retp"]}; 32M - 64K = '
          f'{b["retp"] - a["retp"]} vs 2 x noise {2 * nret}')
    print(f'     set 1 ThrottledCount rate 64K / 4M (mean) / 32M: {a["rate"]:.2f} / {mrate:.2f} / {b["rate"]:.2f} /s')
    print(f'     set 1 accounted peak 64K / 4M / 32M: {a["peak"]} / {statistics.mean(r["peak"] for r in reps):.0f} / '
          f'{b["peak"]}')
    # analyze writes its EXPECTED lines to cluster/analyze/summary.txt, not to analysis.txt (fixed after the first pass)
    an = open(CL + '/analyze/summary.txt').read() if os.path.exists(CL + '/analyze/summary.txt') else ''
    rises = a['retp'] < mret < b['retp'] and b['retp'] - a['retp'] > 2 * nret
    falls = a['rate'] - mrate > 2 * nrate and mrate - b['rate'] > 2 * nrate
    for desc, mineval in (('retained heap rises with Q in set 1', rises), ('ThrottledCount rate falls as Q rises', falls)):
        m = re.search(re.escape(desc) + r'.*— (yes|NO)', an)
        runval = (m.group(1) == 'yes') if m else None
        chk(f'cross-run: "{desc}" recomputed = {mineval}; analyze says {runval}', runval is not None and runval == mineval, '')
for c, h in (('ctla-q64k', 's1q64k'), ('ctla-q32m', 's1q32m')):
    if c in mine and h in mine:
        print(f'     B3h(a) {c}: unheld peak q {mine[c]["peak"]} vs held {mine[h]["peak"]} '
              f'({mine[c]["peak"] / mine[h]["peak"]:.3f}); ThrottledCount {mine[c]["thr"]}; retained {mine[c]["retp"]}')
if 'ctlb' in mine and 's1q64k' in mine:
    cb, ca = mine['ctlb'], mine['s1q64k']
    print(f'     B3h(b): retained ratio {cb["retp"] / ca["retp"]:.3f} vs ceiling ratio {cb["C"] / ca["C"]:.3f}')
if 'ctlc' in mine:
    c = mine['ctlc']
    print(f'     B3h(c): 1 KiB: refusals {c["nref"]}, ThrottledCount {c["thr"]}, peak q {c["peak"]} vs Q {c["Q"]}, '
          f'retained {c["retp"]}, live Mutation {c["live"]}')
print(f'SELFCHECK {"ok" if ok_all else "MISMATCH"}: {nchk["ok"]} ok, {nchk["bad"]} failed')
