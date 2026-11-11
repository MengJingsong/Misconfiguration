#!/usr/bin/env python3
"""Self-check of run 1 (results §5), OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.

Re-parses the raw files with its own code (not the harness's analysis) and applies the frozen rows of the case file:
B2g as amended by S4-A4 (U1..U9, in their order) and B3g as amended by S4-A9 (C1..C7, in their order).
usage: python3 selfcheck.py unit <all-results.txt>
       python3 selfcheck.py cluster <cluster dir with one sub-directory per label>
"""
import csv, json, os, re, statistics, sys

KIB, MIB = 1024, 1 << 20
checks = []


def check(name, ok, note=''):
    checks.append((name, ok))
    print(f'{"PASS" if ok else "FAIL"}  {name}  {note}')


def unit(path):
    recs = []
    for l in open(path):
        if not l.startswith('RESULT '):
            continue
        d = dict(kv.split('=', 1) for kv in l.split()[1:])
        recs.append(d)
    print(f'{len(recs)} RESULT lines')
    check('27 RESULT lines (3 V x 3 runs x 3 methods)', len(recs) == 27)
    for d in recs:
        for k in list(d):
            if k not in ('label', 'hist'):
                d[k] = int(d[k])
    Vs = (16384, 65536, 131072)
    check('lmt = V - 21 in every line', all(d['lmt'] == d['V'] - 21 for d in recs))
    band = {}
    for V in Vs:
        lmt = V - 21
        cap = ((lmt + 10 + 2047) // 2048) * 2048 - 10
        band[V] = cap
    c4 = {V: [d for d in recs if d['V'] == V and d['C'] == 4 << 20] for V in Vs}
    c1 = [d for d in recs if d['V'] == 65536 and d['C'] == 1 << 20]
    for V in Vs:
        check(f'V={V}: six C=4MiB readings', len(c4[V]) == 6)
    med = lambda xs: statistics.median(xs)
    pp = {V: med([d['pendingPeak'] for d in c4[V]]) for V in Vs}
    pd = {V: med([d['poolPeakDelta'] for d in c4[V]]) for V in Vs}
    print('per-V pendingPeak medians', pp)
    print('per-V poolPeakDelta medians', pd, 'span', max(pd.values()) - min(pd.values()), 'B')
    # validity rows
    u5 = [d for d in recs if d['maxFrame'] < d['lmt'] - d['S'] or d['sent'] < d['accepted']]
    u7 = [d for d in recs if d['errors'] > 0]
    u8 = [d for d in recs if d['poolPeakDelta'] < d['maxFrame']]
    u2 = max(pp.values()) - min(pp.values()) > max(d['S'] for d in recs)
    u3 = pd[16384] < pd[65536] < pd[131072] and pd[131072] - pd[16384] > MIB
    c4med65 = pp[65536]
    u4 = [d for d in c1 if not (c4med65 - d['pendingPeak'] > 2 * MIB)]
    u6 = [d for d in recs if d['maxFrame'] > band[d['V']]]
    u9 = (max(pd.values()) - min(pd.values()) >= 300 * KIB) or any(d['poolPeakDelta'] >= MIB for d in recs)
    u1_parts = {
        'every C4M maxFrame in band': all(d['lmt'] - d['S'] <= d['maxFrame'] <= band[d['V']] for V in Vs for d in c4[V]),
        'pendingPeak medians differ <= S': not u2,
        'C1M > 2 MiB below C4M median at 65536': not u4,
        'poolPeakDelta medians span < 300 KiB': max(pd.values()) - min(pd.values()) < 300 * KIB,
        'every poolPeakDelta < 1 MiB': all(d['poolPeakDelta'] < MIB for d in recs),
    }
    print('U5', len(u5), 'U7', len(u7), 'U8', len(u8), 'U2', u2, 'U3', u3, 'U4', len(u4), 'U6', len(u6), 'U9', u9)
    for k, v in u1_parts.items():
        print(f'  U1 part: {k}: {v}')
    if u5:
        verdict = 'U5'
    elif u7:
        verdict = 'U7'
    elif u8:
        verdict = 'U8'
    elif u2:
        verdict = 'U2'
    elif u3:
        verdict = 'U3'
    elif u4:
        verdict = 'U4'
    elif u6:
        verdict = 'U6'
    elif u9:
        verdict = 'U9'
    elif all(u1_parts.values()):
        verdict = 'U1'
    else:
        verdict = 'none'
    print('UNIT VERDICT ROW:', verdict)
    # sub-predictions (B2f, S4-A3)
    bound = {V: 128 * KIB + 2 * (V - 21 + 2 * KIB) for V in Vs}
    for V in Vs:
        mx = max(d['poolPeakDelta'] for d in c4[V] + ([d for d in c1] if V == 65536 else []))
        check(f'sub: V={V} poolPeakDelta <= 128KiB + 2(LMT+2KiB) = {bound[V]}', mx <= bound[V], f'max {mx}')
    check('sub: overflowDelta 0 everywhere', all(d['overflowDelta'] == 0 for d in recs))
    for V, exp in ((16384, 256), (65536, 64), (131072, 32)):
        fr = [d['frames'] for d in c4[V]]
        check(f'sub: V={V} frames about {exp}', all(abs(f - exp) <= 0.1 * exp for f in fr), str(sorted(set(fr))))
    check('sub: pendingPeak in [C-S, C+R] everywhere', all(d['C'] - d['S'] <= d['pendingPeak'] <= d['C'] + d['R'] for d in recs))
    check('sub (S4-A3 expectation): pendingPeak <= C everywhere', all(d['pendingPeak'] <= d['C'] for d in recs),
          str(sorted(set((d['label'], d['pendingPeak']) for d in recs))))
    check('sub: errors 0 and sent = accepted', all(d['errors'] == 0 and d['sent'] == d['accepted'] for d in recs))
    return verdict


def cluster(root):
    labels = ['v16k-1', 'v64k-1', 'v128k-1', 'ctl-1', 'v16k-2', 'v64k-2', 'v128k-2', 'ctl-2']
    S = {}
    for lab in labels:
        D = f'{root}/{lab}'
        if not os.path.isdir(D):
            print('missing', lab); continue
        t = json.load(open(f'{D}/times.json'))
        rows = list(csv.DictReader(open(f'{D}/jmx.csv')))
        def val(r, k):
            try:
                return int(r[k])
            except (ValueError, TypeError):
                return None
        win = [r for r in rows if t['stop'] <= int(r['ms']) <= t['cont']]
        base = [r for r in rows if t['t0'] + 10000 <= int(r['ms']) <= t['t0'] + 25000]
        s = dict(label=lab, V=t['V'], ctl=bool(t.get('ctl')))
        s['pending_peak'] = max(val(r, 'pending') for r in win)
        for k in ('used', 'direct'):
            s[f'{k}_delta'] = max(val(r, k) for r in win) - statistics.median(val(r, k) for r in base)
        s['nwin'], s['nbase'] = len(win), len(base)
        log = open(f'{D}/n1-system.log', errors='replace').read()
        s['down_all'] = len(re.findall(r'is now DOWN', log))
        s['down'] = 0   # C4: only DOWN lines inside [SIGSTOP, SIGCONT]; log time stamps are UTC
        import calendar, time
        for m in re.finditer(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3}) .*is now DOWN', log):
            ms = calendar.timegm(time.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S')) * 1000 + int(m.group(2))
            if t['stop'] <= ms <= t['cont']:
                s['down'] += 1
        s['frame_err'] = len(re.findall(r'Maximum payload size', log))
        s['errors'] = len(re.findall(r'^ERROR', log, re.M))
        y = open(f'{D}/n1-cassandra.yaml').read()
        s['yaml_ok'] = all(x in y for x in (
            f'internode_application_send_queue_capacity: {16 if s["ctl"] else 1}MiB',
            f'internode_application_receive_queue_reserve_endpoint_capacity: {16 if s["ctl"] else 2}MiB',
            f'internode_application_send_queue_reserve_global_capacity: {32 if s["ctl"] else 4}MiB'))
        st = open(f'{D}/stress.log', errors='replace').read()
        m = re.search(r'^Op rate\s*:\s*([\d,]+)', st, re.M); s['rate'] = m.group(1) if m else None
        m = re.search(r'^Total errors\s*:\s*([\d,]+)', st, re.M); s['stress_err'] = m.group(1) if m else None
        S[lab] = s
        print(json.dumps(s))
    check('8 lifetimes', len(S) == 8)
    check('yaml knobs as B3b + S4-A6 in every lifetime', all(s['yaml_ok'] for s in S.values()))
    valid = lambda s: s['down'] == 0 and s['frame_err'] == 0
    main = [s for s in S.values() if not s['ctl'] and valid(s)]
    ctl = [s for s in S.values() if s['ctl'] and valid(s)]
    per = {}
    for V in (16384, 65536, 131072):
        rs = [s for s in main if s['V'] == V]
        per[V] = {k: statistics.mean(s[k] for s in rs) if rs else None for k in ('pending_peak', 'used_delta', 'direct_delta')}
        per[V]['n'] = len(rs)
    print('per-V', per)
    cap, ccap, msg = 3 * MIB, 32 * MIB, 2 * KIB
    c4 = [s['label'] for s in S.values() if s['down']]
    c5 = [s['label'] for s in S.values() if s['frame_err']]
    noV = [V for V in per if per[V]['n'] == 0]
    c2 = [k for k in ('pending_peak', 'used_delta', 'direct_delta')
          if None not in [per[V][k] for V in per] and per[16384][k] < per[65536][k] < per[131072][k]
          and per[131072][k] - per[16384][k] > MIB]
    c3 = [s['label'] for s in main if s['pending_peak'] < 0.9 * cap] + [s['label'] for s in ctl if s['pending_peak'] < 0.9 * ccap]
    c6 = [s['label'] for s in main if s['pending_peak'] > cap + msg] + [s['label'] for s in ctl if s['pending_peak'] > ccap + msg]
    span = lambda k: max(per[V][k] for V in per) - min(per[V][k] for V in per)
    bands = {
        'main pending in band': all(0.9 * cap <= s['pending_peak'] <= cap + msg for s in main),
        'pending span < 5%': span('pending_peak') < 0.05 * statistics.mean(per[V]['pending_peak'] for V in per),
        'UsedSize span < 0.5 MiB': span('used_delta') < 0.5 * MIB,
        'direct span < 1 MiB': span('direct_delta') < MIB,
        'control pending in band': all(0.9 * ccap <= s['pending_peak'] <= ccap + msg for s in ctl) and len(ctl) > 0,
    }
    print('C4', c4, 'C5', c5, 'noV', noV, 'C2', c2, 'C3', c3, 'C6', c6)
    print('spans: pending', span('pending_peak'), 'used', span('used_delta'), 'direct', span('direct_delta'))
    for k, v in bands.items():
        print(f'  C1 band: {k}: {v}')
    if noV:
        verdict = 'C4/C5 (no counting run for a V)'
    elif c2:
        verdict = 'C2'
    elif c3:
        verdict = 'C3'
    elif c6:
        verdict = 'C6'
    elif not all(bands.values()):
        verdict = 'C7'
    else:
        verdict = 'C1'
    print('CLUSTER VERDICT ROW:', verdict)
    return verdict


if __name__ == '__main__':
    v = unit(sys.argv[2]) if sys.argv[1] == 'unit' else cluster(sys.argv[2])
    print(f'{sum(1 for _, ok in checks if ok)}/{len(checks)} checks pass; verdict row {v}')
