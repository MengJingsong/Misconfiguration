#!/usr/bin/env python3
"""Analysis of batch_size_warn_threshold-verifyBatchSize-size--autonomous, both tiers (B2f/B2g, B3f/B3g as amended A1-A8).
usage: analyze.py unit <file with arm/req/STAGE4 lines> <Byteman trace>
       analyze.py cluster <cluster output dir>        (requests.txt, trace-all.txt, phases.csv, gc-*.log, system-*.log)
Prints one table row per arm/phase and EXPECTED lines for every part of the prediction. It prints readings and checks; the AI
matches them to a row of B2g/B3g in the results file. Arms are delimited by 'arm <name> begin|end ms=' lines; Byteman lines
(dec/exe/bst/siz/rej, Alloc.java format) are joined to an arm by their ms stamp."""
import csv, datetime, glob, os, re, statistics, sys

tier = sys.argv[1]
KiB = 1024


def expect(desc, cond):
    print(f'EXPECTED: {desc} — {"yes" if cond else "NO"}')
    return cond


def parse_kv(line):
    return dict(kv.split('=', 1) for kv in line.split()[1:] if '=' in kv)


def load(reqf, tracef):
    reqs, win = [], {}
    for l in open(reqf):
        if l.startswith('req '):
            d = parse_kv(l)
            for k in ('k', 'parts', 'rows', 'nominal', 'warns', 'wsize', 'ms0', 'ms1'):
                d[k] = int(d[k])
            reqs.append(d)
        elif l.startswith('arm '):
            p = l.split()
            m = int(re.search(r'ms=(\d+)', l).group(1))
            win.setdefault(p[1], {})[p[2]] = m
    tr = []
    for l in open(tracef):
        p = l.split()
        if not p or p[0] not in ('dec', 'exe', 'bst', 'siz', 'rej'):
            continue
        d = {'tag': p[0]}
        for kv in p[1:]:
            if '=' in kv:
                a, b = kv.split('=', 1)
                d[a] = b
        d['ms'] = int(d['ms'])
        for k in ('bytes', 'n', 'size', 'warn', 'fail'):
            if k in d:
                d[k] = int(d[k])
        tr.append(d)
    return reqs, win, tr


def arm_stats(name, reqs, win, tr):
    rs = [d for d in reqs if d['arm'] == name]
    w = win.get(name, {})
    lo, hi = w.get('begin', 0), w.get('end', 1 << 62)
    ls = [d for d in tr if lo <= d['ms'] <= hi + 200]
    by = {t: [d for d in ls if d['tag'] == t] for t in ('dec', 'exe', 'bst', 'siz', 'rej')}
    oc = {}
    for d in rs:
        o = d['outcome'] if d['outcome'] == 'ok' else 'ERR:' + d['outcome'].split(':', 2)[2][:30]
        oc[o] = oc.get(o, 0) + 1

    def med(t, key='bytes'):
        v = [d[key] for d in by[t] if key in d and d[key] >= 0]
        return statistics.median(v) if v else None
    return {'name': name, 'n': len(rs), 'oc': oc, 'warns': sum(d['warns'] for d in rs), 'warn_reqs': sum(1 for d in rs if d['warns'] > 0),
            'wsizes': sorted({d['wsize'] for d in rs if d['wsize'] >= 0}), 'nsiz': len(by['siz']), 'nrej': len(by['rej']),
            'sizes': sorted({d['size'] for d in by['siz']}), 'siz_n': sorted({d['n'] for d in by['siz']}),
            'siz_warn': sorted({d['warn'] for d in by['siz']}), 'siz_fail': sorted({d['fail'] for d in by['siz']}),
            'bst': med('bst'), 'dec': med('dec'), 'exe': med('exe'),
            'bst_list': [d['bytes'] for d in by['bst']], 'ok': oc.get('ok', 0)}


def band_ok(a, b):
    """A2: medians differ by at most 10 % of the larger or 16 KiB, whichever is larger"""
    return abs(a - b) <= max(0.10 * max(a, b), 16 * KiB)


def table(stats):
    print('arm | n | outcomes | client warns | siz lines | rej lines | dataSize values | siz warn/fail B | bst med (min..max) | dec med | exe med')
    for s in stats:
        bl = s['bst_list']
        rng = f"({min(bl)}..{max(bl)})" if bl else ''
        print(f"{s['name']} | {s['n']} | {s['oc']} | {s['warns']} | {s['nsiz']} | {s['nrej']} | {s['sizes'][:3]}{'...' if len(s['sizes']) > 3 else ''} | "
              f"{s['siz_warn']}/{s['siz_fail']} | {s['bst']} {rng} | {s['dec']} | {s['exe']}")


def unit():
    reqf, tracef = sys.argv[2], sys.argv[3]
    reqs, win, tr = load(reqf, tracef)
    lines = open(reqf).read().splitlines()
    rows = {m.group(1): int(m.group(2)) for l in lines for m in [re.match(r'STAGE4 rows arm=(\S+) count=(\d+)', l)] if m}
    knobs = {}
    for l in lines:
        m = re.match(r'STAGE4 arm (\S+) knobs warn_kib=(\d+) warn_bytes=(\d+) fail_kib=(\d+) fail_bytes=(\d+)', l)
        if m:
            knobs[m.group(1)] = tuple(int(x) for x in m.groups()[1:])
    names = []
    for d in reqs:
        if d['arm'] not in names:
            names.append(d['arm'])
    stats = [arm_stats(a, reqs, win, tr) for a in names]
    S = {s['name']: s for s in stats}
    print(f'tier unit: {len(reqs)} requests in {len(names)} arms')
    table(stats)
    print('rows (SELECT count(*)):', rows)
    # validity
    exp_arms = [f'w{w}-p{p}' for w in (1, 5, 1024, 65536) for p in (20, 200)] + ['sp-w1', 'fc', 'inv']
    expect(f'V1 all {len(exp_arms)} arms ran with 20 requests each', all(a in S and S[a]['n'] == 20 for a in exp_arms))
    expect('V2 every request reached verifyBatchSize (one siz line per request) in every arm', all(S[a]['nsiz'] == S[a]['n'] for a in exp_arms if a in S))
    wk = {'fc': (5, 10), 'inv': (200, 10), 'sp-w1': (1, 100000)}
    ok_knobs = True
    for a in exp_arms:
        if a not in S:
            ok_knobs = False
            continue
        w, f = wk.get(a, (int(re.match(r'w(\d+)', a).group(1)) if a.startswith('w') else 0, 100000))
        k = knobs.get(a)
        if not k or k[0] != w or k[1] != w * 1024 or k[2] != f or k[3] != f * 1024 or S[a]['siz_warn'] != [w * 1024] or S[a]['siz_fail'] != [f * 1024]:
            ok_knobs = False
    expect('V3 knob values read back and seen by the check (siz warn/fail bytes equal the set values) in every arm', ok_knobs)
    # multi-partition arms' mutation counts and dataSize in range
    mp = [a for a in exp_arms if a.startswith('w') or a in ('fc', 'inv')]
    expect('V4 multi-partition batches carry 20 / 200 mutations (siz n)', all(S[a]['siz_n'] == [20 if a.endswith('p20') or a in ('fc', 'inv') else 200] for a in mp if a in S))
    expect('V5 sp-w1 is a single mutation (siz n=1)', S['sp-w1']['siz_n'] == [1])
    sz20 = {a: S[a]['sizes'] for a in exp_arms if a.endswith('p20') and a in S}
    sz200 = {a: S[a]['sizes'] for a in exp_arms if a.endswith('p200') and a in S}
    allp20 = sorted({v for x in sz20.values() for v in x}); allp200 = sorted({v for x in sz200.values() for v in x})
    expect(f'V6 dataSize of the 20-partition batch is in (5 KiB, 1024 KiB) and of the 200-partition batch in (5 KiB, 1024 KiB): {allp20[:1]}..{allp20[-1:]} / {allp200[:1]}..{allp200[-1:]}',
           bool(allp20) and bool(allp200) and min(allp20) > 5 * KiB and max(allp20) < 1024 * KiB and min(allp200) > 5 * KiB and max(allp200) < 1024 * KiB)
    # prediction
    for p, parts in (('p20', 20), ('p200', 200)):
        for w in (1, 5):
            a = f'w{w}-{p}'
            s = S[a]
            expect(f'P1 {a}: every batch warned (client warns {s["warns"]}/{s["n"]} requests with a warning {s["warn_reqs"]}), none thrown, rows {rows.get(a)} == {s["n"] * parts}',
                   s['warn_reqs'] == s['n'] and s['ok'] == s['n'] and rows.get(a) == s['n'] * parts)
        for w in (1024, 65536):
            a = f'w{w}-{p}'
            s = S[a]
            expect(f'P2 {a}: no warning ({s["warns"]}), none thrown, rows {rows.get(a)} == {s["n"] * parts}', s['warns'] == 0 and s['ok'] == s['n'] and rows.get(a) == s['n'] * parts)
        allsz = {tuple(S[f'w{w}-{p}']['sizes']) for w in (1, 5, 1024, 65536)}
        expect(f'P3 {p}: dataSize values identical across the four warn values ({sorted(allsz)[:1]})', len(allsz) == 1 and len(next(iter(allsz))) >= 1)
        meds = {w: S[f'w{w}-{p}']['bst'] for w in (1, 5, 1024, 65536)}
        expect(f'P4 {p}: coordinator allocation (bst) medians within 10 %/16 KiB across warn values {meds}',
               all(band_ok(meds[x], meds[y]) for x in meds for y in meds if x < y))
        wsz = [S[f'w{w}-{p}']['wsizes'] for w in (1, 5)]
        expect(f'P3b {p}: the size in the client warning equals the check operand', all(x == S[f"w1-{p}"]['sizes'] for x in wsz))
    s = S['sp-w1']
    expect(f'P5 sp-w1: single-partition batch: no warning ({s["warns"]}), none thrown, rows {rows.get("sp-w1")} == {s["n"] * 20}', s['warns'] == 0 and s['ok'] == s['n'] and rows.get('sp-w1') == s['n'] * 20)
    s = S['fc']
    expect(f'C1 fc (warn 5 KiB, fail 10 KiB): all {s["n"]} rejected with "Batch too large" ({s["oc"]}), rej lines {s["nrej"]}, rows {rows.get("fc")} == 0',
           s['oc'] == {'ERR:Batch_too_large': s['n']} and s['nrej'] == s['n'] and rows.get('fc') == 0)
    s = S['inv']
    expect(f'I1 inv (warn 200 KiB, fail 10 KiB): accepted ({s["oc"]}), no warning ({s["warns"]}), rej {s["nrej"]}, rows {rows.get("inv")} == {s["n"] * 20}',
           s['ok'] == s['n'] and s['warns'] == 0 and s['nrej'] == 0 and rows.get('inv') == s['n'] * 20)
    hl = [l for l in lines if l.startswith('STAGE4 heap')]
    print('info (not a prediction):', *hl[:3], '...', sep='\n  ')


def gc_post(path):
    out = []
    if not os.path.exists(path):
        return out
    for l in open(path):
        m = re.match(r'\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)\+0000\].*?(\d+)M->(\d+)M\((\d+)M\)', l)
        if m:
            t = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S.%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000
            out.append((t, int(m.group(3))))
    return out


def cluster():
    D = sys.argv[2]
    reqs, win, tr = load(D + '/requests.txt', D + '/trace-all.txt')
    ph = list(csv.DictReader(open(D + '/phases.csv')))
    P = {r['phase']: r for r in ph}
    stats = [arm_stats(r['phase'], reqs, win, tr) for r in ph]
    S = {s['name']: s for s in stats}
    print(f'tier cluster: {len(reqs)} requests in {len(ph)} phases')
    table(stats)
    print('phase | lifetime | disk bytes (data dir after flush) | writes (WriteLatency Count) delta | heap poll max | post-GC max (MiB) in window')
    gcs = {}
    for r in ph:
        life = r['lifetime']
        if life not in gcs:
            gcs[life] = gc_post(f'{D}/gc-{life}.log')
        lo, hi = float(win[r['phase']]['begin']), float(win[r['phase']]['end'])
        pm = [v for t, v in gcs[life] if lo <= t <= hi + 1000]
        r['gc_post_max'] = max(pm) if pm else None
        r['gc_n'] = len(pm)
        r['wdelta'] = int(r['writes_after']) - int(r['writes_before'])
        print(f"{r['phase']} | {life} | {r['disk_bytes']} | {r['wdelta']} | {r['heap_poll_max']} | {r['gc_post_max']} ({r['gc_n']} collections)")
    sysl = {}
    for f in sorted(glob.glob(D + '/system-*.log')):
        life = os.path.basename(f)[7:-4]
        txt = open(f, errors='replace').read().splitlines()
        sysl[life] = {'warn': sum(1 for l in txt if re.match(r'WARN\s.*Batch for \[ks\.t\] is of size', l)),
                      'err': sum(1 for l in txt if re.match(r'ERROR\s.*Batch for \[ks\.t\] is of size', l))}
    print('system.log counts per lifetime:', sysl)
    n1, n2 = 2000, 20
    kind = lambda p: p.split('-')[-1]
    # validity
    expect('V1 every request reached verifyBatchSize (one siz line per request) in every phase', all(s['nsiz'] == s['n'] for s in stats))
    expw = {'L1': 5 * KiB, 'L1live': 90000 * KiB, 'L2': 90000 * KiB, 'L3': 5 * KiB}
    expf = {'L1': 100000 * KiB, 'L1live': 100000 * KiB, 'L2': 100000 * KiB, 'L3': 20 * KiB}
    bad = []
    for r in ph:
        s = S[r['phase']]
        w = 200 * KiB if r['phase'] == 'L3-inv' else expw[r['lifetime']]
        if s['siz_warn'] != [w] or s['siz_fail'] != [expf[r['lifetime']]]:
            bad.append((r['phase'], s['siz_warn'], s['siz_fail']))
    expect(f'V2 the check saw the intended warn and fail values (JMX/yaml) in every phase — mismatches {bad}', not bad)
    expect('V3 the batch dataSize is above 5 KiB in every phase (the lowest warn value is exceeded): ' + str({s['name']: min(s['sizes']) for s in stats if s['sizes']}),
           all(s['sizes'] and min(s['sizes']) > 5 * KiB for s in stats))
    # prediction: warn lifetimes
    for r in ph:
        life, name = r['lifetime'], r['phase']
        if life in ('L1', 'L2', 'L1live') and name.split('-')[-1].startswith('W'):
            s = S[name]
            n = n1 if kind(name).startswith('W1') else n2
            parts = 50 if kind(name).startswith('W1') else 20480
            exp_warn = n if life == 'L1' else 0
            expect(f'P1 {name}: client warnings {s["warns"]} == {exp_warn}, outcomes {s["oc"]} all ok, writes {r["wdelta"]} == {n * parts}',
                   s['warns'] == exp_warn and s['ok'] == s['n'] == n and r['wdelta'] == n * parts)
    for life in ('L1', 'L2'):
        if life in sysl:
            want = 2 * (n1 + n2) if life == 'L1' else 0
            tot = sysl[life]['warn'] - (0)
            expect(f'P2 {life}: system.log "Batch for [ks.t] is of size" WARN lines {sysl[life]["warn"]} == {want}', sysl[life]['warn'] == want)
    # flatness across lifetimes
    for a, b in (('L1', 'L2'),):
        for k in ('W1a', 'W1b', 'W2a', 'W2b'):
            pa, pb = f'{a}-{k}', f'{b}-{k}'
            if pa not in S or pb not in S:
                continue
            ba, bb = S[pa]['bst'], S[pb]['bst']
            da, db = int(P[pa]['disk_bytes']), int(P[pb]['disk_bytes'])
            ga, gb = P[pa]['gc_post_max'], P[pb]['gc_post_max']
            rel = lambda x, y: abs(x - y) / max(x, y, 1)
            expect(f'P3 {pa} vs {pb}: coordinator allocation {ba} vs {bb} (within 10 %/16 KiB)', band_ok(ba, bb))
            expect(f'P4 {pa} vs {pb}: data bytes after flush {da} vs {db}: relative difference {rel(da, db):.3f} (<= 0.10)', rel(da, db) <= 0.10)
            expect(f'P5 {pa} vs {pb}: writes {P[pa]["wdelta"]} == {P[pb]["wdelta"]}', P[pa]['wdelta'] == P[pb]['wdelta'])
            if ga is not None and gb is not None:
                print(f'INFO post-GC max occupancy {pa} {ga} MiB vs {pb} {gb} MiB: relative difference {rel(ga, gb):.3f} (10 % equal, 25 % refuted band)')
    # live switch
    for k in ('W1', 'W2'):
        pl = f'L1live-{k}'
        if pl in S:
            s = S[pl]
            expect(f'P6 {pl}: after the live change to 90000KiB no warning ({s["warns"]}), all ok, bst {s["bst"]}', s['warns'] == 0 and s['ok'] == s['n'])
    # control
    if 'L3-ctl' in S:
        s, r = S['L3-ctl'], P['L3-ctl']
        e = sysl.get('L3', {}).get('err')
        expect(f'C1 L3-ctl (warn 5 KiB, fail 20 KiB): all {s["n"]} rejected "Batch too large" ({s["oc"]}), rej {s["nrej"]}, writes {r["wdelta"]} == 0, ERROR log lines {e}',
               s['oc'] == {'ERR:Batch_too_large': s['n']} and s['nrej'] == s['n'] and r['wdelta'] == 0 and e == s['n'])
        expect(f'C2 L3-ctl disk bytes after flush {r["disk_bytes"]} <= 1 MiB (no sstable data)', int(r['disk_bytes']) <= (1 << 20))
        w1 = int(P['L1-W1a']['disk_bytes']) if 'L1-W1a' in P else 0
        print(f'INFO the same workload accepted (L1-W1a) leaves {w1} bytes; rejected leaves {r["disk_bytes"]}')
    if 'L3-inv' in S:
        s, r = S['L3-inv'], P['L3-inv']
        expect(f'I1 L3-inv (fail 20 KiB, warn 200 KiB): accepted ({s["oc"]}), warns {s["warns"]}, rej {s["nrej"]}, writes {r["wdelta"]} == {s["n"] * 50}',
               s['ok'] == s['n'] and s['warns'] == 0 and s['nrej'] == 0 and r['wdelta'] == s['n'] * 50)
    print('INFO bst of W2 (20 MiB batch), warn 5 KiB vs 90000 KiB:', {k: S[k]['bst'] for k in S if 'W2' in k})


if __name__ == '__main__':
    unit() if tier == 'unit' else cluster()
