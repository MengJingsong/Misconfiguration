#!/usr/bin/env python3
"""Independent self-check of run 1, native_transport_receive_queue_capacity-acquireCapacity-queueCapacity (results §5).

Re-parses the raw files on the node, without the run script's code: the node's trace (ntq.trace, one per label), each
arm's client output (flood-*.out), meters.txt and class histograms (histo-*.txt), and the unit tier's harness.out.
It (1) checks the trace's own integrity (per handler, every acquire and release moves queueSize by exactly its bytes),
(2) recomputes every number the frozen §9a predictions use, with its own arm boundaries (the client's connection
addresses matched to the trace's `new` lines), (3) judges each prediction again, and (4) compares its numbers with the
run script's arms.csv. Prints one line per check, "ok" or "FAIL", and a summary; exit 1 on any FAIL.
usage: selfcheck.py [<logs root>]     (default ~/stage4-logs/ntq/run1)"""
import csv, glob, math, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/ntq/run1')
KIB, MIB = 1024, 1 << 20
RES = 4 * MIB
CAP = {'c128k': 128 * KIB, 'c512k': 512 * KIB, 'c1m': MIB, 'c4m': 4 * MIB, 'nsweep': MIB, 'defres': 512 * KIB}
PINNED = {k: k != 'defres' for k in CAP}
res = {'ok': 0, 'FAIL': 0}


def chk(name, cond, detail=''):
    res['ok' if cond else 'FAIL'] += 1
    print(f'{"ok  " if cond else "FAIL"} {name} {detail}')


def kv(line):
    """'kind a=1 b=x ...' -> (kind, dict)"""
    parts = line.split()
    d = {}
    for p in parts[1:]:
        if '=' in p:
            k, v = p.split('=', 1)
            d[k] = v
    return parts[0], d


def read_trace(path):
    handlers, events = {}, []
    with open(path, errors='replace') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line:
                continue
            kind, d = kv(line)
            if kind == 'new':
                handlers[d['id']] = dict(throw=d['throw'] == 'true', cap=int(d['cap']), remote=d['remote'].lstrip('/'))
            elif kind in ('acq', 'rel', 'dec', 'rls', 'disc', 'ldisc', 'wake'):
                events.append((kind, d))
    return handlers, events


def flood(path):
    conns, total, texts = [], None, []
    for line in open(path):
        if line.startswith('conn '):
            conns.append(re.search(r'local=/?(\S+)', line).group(1))
        elif line.startswith('TOTAL'):
            total = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', line)}
        elif line.startswith(('ovl_other_text', 'err_text')):
            texts.append(line.strip())
    return conns, total, texts


def meters(path):
    txt = open(path).read()
    m = re.search(r'^delta (\{.*\})$', txt, re.M)
    return eval(m.group(1)) if m else {}


def histo(path):
    qm = 0
    for line in open(path):
        f = line.split()
        if len(f) >= 4 and f[3] == 'org.apache.cassandra.transport.messages.QueryMessage':
            qm = int(f[1])
    return qm


def arms_csv(label_dir):
    p = label_dir + '/arms.csv'
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return {r['arm']: r for r in csv.DictReader(f)}


def replay(ids, events):
    """per handler state and sums, in file order; returns dict of readings"""
    q = {i: 0 for i in ids}
    d = {i: 0 for i in ids}
    st = {i: dict(succ=0, ref=0, dec=0, bif=0, rls=0, disc=0, ldisc=0, wake=0) for i in ids}
    integ = 0
    sa = sd = 0
    pa = pd = 0
    over_k = []
    d_over_a = 0
    series = []
    M = None
    for kind, e in events:
        i = e.get('id')
        if i not in q:
            continue
        ms = int(e['ms'])
        b = int(e.get('b', 0))
        if kind == 'acq':
            qa = int(e['q'])
            if e['out'] == 'SUCCESS':
                st[i]['succ'] += 1
                if qa != q[i] + b:
                    integ += 1
            else:
                st[i]['ref'] += 1
                if qa != q[i]:
                    integ += 1
            sa += qa - q[i]; q[i] = qa
        elif kind == 'rel':
            qa = int(e['q'])
            if qa != q[i] - b:
                integ += 1
            sa += qa - q[i]; q[i] = qa
        elif kind == 'dec':
            st[i]['dec'] += 1
            if e['bp'] == 'BYTES_IN_FLIGHT':
                st[i]['bif'] += 1
            d[i] += b; sd += b
            if M is None:
                M = b
        elif kind == 'rls':
            st[i]['rls'] += 1
            d[i] -= b; sd -= b
        elif kind in ('disc', 'ldisc', 'wake'):
            st[i][kind] += 1
        pa, pd = max(pa, sa), max(pd, sd)
        if sd > sa:
            d_over_a += 1
        series.append((ms, sa, sd))
    return dict(q=q, d=d, st=st, integ=integ, pa=pa, pd=pd, d_over_a=d_over_a, series=series, M=M, sa=sa, sd=sd)


def tot(r, k):
    return sum(s[k] for s in r['st'].values())


def main():
    # ---------------- unit tier
    for u in ('unit',):
        p = f'{ROOT}/{u}/harness.out'
        if os.path.exists(p):
            lines = [l for l in open(p) if l.startswith('STAGE4 check')]
            bad = [l for l in lines if 'MISMATCH' in l]
            chk(f'unit: STAGE4 checks all ok', len(lines) > 0 and not bad, f'({len(lines)} checks, {len(bad)} mismatches)')
        s = f'{ROOT}/{u}/summary.txt'
        if os.path.exists(s):
            txt = open(s).read()
            for cls in ('ClientResourceLimitsTest', 'NativeQueueModesTest'):
                m = re.search(cls + r' exit=(\d+) Tests run: (\d+), Failures: (\d+), Errors: (\d+)', txt)
                chk(f'unit: {cls} passed', bool(m) and m.group(1) == '0' and m.group(3) == '0' and m.group(4) == '0',
                    m.group(0) if m else 'no line')

    # ---------------- cluster tier
    for label in ('c128k', 'c512k', 'c1m', 'c4m', 'nsweep', 'defres'):
        L = f'{ROOT}/{label}'
        tp = L + '/ntq.trace'
        if not os.path.exists(tp):
            print(f'--   {label}: no trace')
            continue
        handlers, events = read_trace(tp)
        ac = arms_csv(L)
        cap = CAP[label]
        print(f'==== {label}: {len(handlers)} handlers, {len(events)} events')
        for armdir in sorted(glob.glob(L + '/*/')):
            arm = os.path.basename(armdir.rstrip('/'))
            outs = sorted(glob.glob(armdir + 'flood-*.out'))
            if not outs:
                continue
            conns, totals = [], {}
            texts = []
            for o in outs:
                c, t, x = flood(o)
                conns += c; texts += x
                if t:
                    for k, v in t.items():
                        totals[k] = totals.get(k, 0) + v
            ids = [i for i, h in handlers.items() if h['remote'] in conns]
            n = len(ids)
            r = replay(set(ids), events)
            M = r['M']
            dm = meters(armdir + 'meters.txt') if os.path.exists(armdir + 'meters.txt') else {}
            K = n * cap + RES if PINNED[label] else None
            row = ac.get(arm, {})
            ref, succ, dec, bif = tot(r, 'ref'), tot(r, 'succ'), tot(r, 'dec'), tot(r, 'bif')
            disc, ldisc = tot(r, 'disc'), tot(r, 'ldisc')
            final = [r['q'][i] for i in ids]
            throws = {handlers[i]['throw'] for i in ids}
            caps = {handlers[i]['cap'] for i in ids}
            print(f'-- {label}/{arm}: n={n} throw={throws} cap={caps} M={M} succ={succ} ref={ref} dec={dec} bif={bif} '
                  f'disc={disc} ldisc={ldisc} peakA={r["pa"]} peakD={r["pd"]} K={K} client={totals} meters={dm}')
            chk(f'{label}/{arm}: trace integrity (every acquire/release moves queueSize by its bytes)', r['integ'] == 0,
                f'({r["integ"]} violations)')
            chk(f'{label}/{arm}: read-back cap', caps <= {cap}, str(caps))
            if arm == 'connidle':
                chk(f'{label}/{arm}: 20 handlers, 10 per mode', n == 20 and sum(handlers[i]['throw'] for i in ids) == 10)
                chk(f'{label}/{arm}: no acquire, no decode', succ + ref + dec == 0)
                continue
            # agreement with the run script
            if row:
                for k, v in (('succ', succ), ('ref', ref), ('dec', dec), ('dec_bif', bif), ('disc', disc),
                             ('ldisc', ldisc), ('peakA', r['pa']), ('peakD', r['pd']), ('handlers', n)):
                    chk(f'{label}/{arm}: agrees with arms.csv on {k}', str(v) == row.get(k), f'({v} vs {row.get(k)})')
            chk(f'{label}/{arm}: client got every response', totals.get('outstanding') == 0, str(totals.get('outstanding')))
            chk(f'{label}/{arm}: no other overload (client ovl_other/err, TimedOutBeforeProcessing, ProtocolException)',
                totals.get('ovl_other') == 0 and totals.get('err') == 0 and dm.get('TimedOutBeforeProcessing') == 0
                and dm.get('ProtocolException') == 0, str(texts[:2]))
            hs = sorted(glob.glob(armdir + 'histo-*.txt'))
            hq = [histo(h) for h in hs]
            if row.get('histos'):
                chk(f'{label}/{arm}: histogram counts agree with arms.csv', [int(x.split('/')[0]) for x in
                                                                             row['histos'].split(';')] == hq, f'{hq}')
            kind = row.get('kind', '')
            # P6: each histogram's live QueryMessage count within sumD/M over its wall interval +-1 s (the interval is
            # read from the run's summary line "<arm>: histogram k <t0>-<t1> ms")
            summ = open(L + '/summary.txt').read() if os.path.exists(L + '/summary.txt') else ''
            for k, qmk in enumerate(hq):
                m = re.search(r'^' + re.escape(arm) + r': histogram ' + str(k + 1) + r' (\d+)-(\d+) ms', summ, re.M)
                if not m or not M:
                    chk(f'{label}/{arm}: P6 histogram {k + 1} interval found', False)
                    continue
                h0, h1 = int(m.group(1)), int(m.group(2))
                win = [x for ms, _, x in r['series'] if h0 - 1000 <= ms <= h1 + 1000]
                chk(f'{label}/{arm}: P6 histogram {k + 1} QueryMessage within sumD/M over its interval +-1 s',
                    bool(win) and min(win) / M <= qmk <= max(win) / M,
                    f'({qmk} in [{min(win) / M if win else None}, {max(win) / M if win else None}])')
            if arm.startswith('A_'):
                bound = n * (cap // M) * M
                chk(f'{label}/{arm}: P4 no refusal, discard, warning', ref == 0 and disc + ldisc == 0
                    and dm.get('RequestDiscarded') == 0 and totals.get('warned') == 0)
                chk(f'{label}/{arm}: P4 peak sumA <= N floor(C/M) M', r['pa'] <= bound, f'({r["pa"]} <= {bound})')
                chk(f'{label}/{arm}: P4 every handler ends at 0', set(final) == {0}, str(set(final)))
            elif arm in ('Bts', 'Btl') or (arm.startswith('n') and n > 1):
                chk(f'{label}/{arm}: P1/P5 refusals occur', ref > 0, str(ref))
                chk(f'{label}/{arm}: P1/P5 peak sumA <= K and > K - 2M', K - 2 * M < r['pa'] <= K,
                    f'({K - 2 * M} < {r["pa"]} <= {K})')
                chk(f'{label}/{arm}: P1/P5 every sumA <= K', max(sa for _, sa, _ in r['series']) <= K)
                chk(f'{label}/{arm}: P1 sumD <= sumA at every line', r['d_over_a'] == 0, str(r['d_over_a']))
                chk(f'{label}/{arm}: P1 refusals = RequestDiscarded = client ovl_bytes',
                    ref == dm.get('RequestDiscarded') == totals.get('ovl_bytes'),
                    f'({ref}, {dm.get("RequestDiscarded")}, {totals.get("ovl_bytes")})')
                chk(f'{label}/{arm}: P1 every refusal discarded, none decoded',
                    (disc if M < 131071 else ldisc) == ref and dec == succ, f'(disc {disc} ldisc {ldisc} dec {dec} succ {succ})')
                chk(f'{label}/{arm}: P1 every handler ends at 0', set(final) == {0}, str(set(final)))
            elif arm == 'n1':
                chk(f'{label}/{arm}: P5 N=1 no refusal', ref == 0)
                chk(f'{label}/{arm}: P5 N=1 peak sumA = 32 M', r['pa'] == 32 * M, f'({r["pa"]} vs {32 * M})')
            elif arm == 'Bdl':
                chk(f'{label}/{arm}: P2 refusals occur', ref > 0, str(ref))
                chk(f'{label}/{arm}: P2 no error/warning to the client, RequestDiscarded +0',
                    totals.get('ovl_bytes') == 0 and totals.get('warned') == 0 and dm.get('RequestDiscarded') == 0)
                chk(f'{label}/{arm}: P2 per handler decodes = successful acquires',
                    all(r['st'][i]['dec'] == r['st'][i]['succ'] for i in ids) and bif == 0)
                chk(f'{label}/{arm}: P2 peak sumA in (K - 2M, K]', K - 2 * M < r['pa'] <= K, f'({r["pa"]})')
                chk(f'{label}/{arm}: P2 sumD <= sumA at every line', r['d_over_a'] == 0, str(r['d_over_a']))
                chk(f'{label}/{arm}: P2 every handler ends at 0', set(final) == {0}, str(set(final)))
            elif arm == 'Bds':
                chk(f'{label}/{arm}: P3 refusals occur', ref > 0, str(ref))
                chk(f'{label}/{arm}: P3 per handler refusals = decodes with BYTES_IN_FLIGHT; total = client warned',
                    all(r['st'][i]['bif'] == r['st'][i]['ref'] for i in ids) and bif == ref == totals.get('warned'),
                    f'({bif}, {ref}, {totals.get("warned")})')
                chk(f'{label}/{arm}: P3 RequestDiscarded +0, no overload error',
                    dm.get('RequestDiscarded') == 0 and totals.get('ovl_bytes') == 0)
                chk(f'{label}/{arm}: P3 drift: every handler ends at -k_i M',
                    all(r['q'][i] == -r['st'][i]['ref'] * M for i in ids), f'(sum {sum(final)}, -sum k M {-ref * M})')
                chk(f'{label}/{arm}: P3 peak sumD > K', r['pd'] > K, f'({r["pd"]} > {K})')
                t0 = int(row['t_start']) if row.get('t_start') else r['series'][0][0]
                dur = float(row['s']) * 1000 if row.get('s') else None
                if dur:
                    first = [x for ms, _, x in r['series'] if t0 <= ms < t0 + dur / 3]
                    last = [x for ms, _, x in r['series'] if t0 + 2 * dur / 3 <= ms <= t0 + dur]
                    chk(f'{label}/{arm}: P3 mean sumD last third > first third',
                        bool(first) and bool(last) and sum(last) / len(last) > sum(first) / len(first),
                        f'({sum(last) / max(1, len(last)):.0f} vs {sum(first) / max(1, len(first)):.0f})')
                if len(hq) == 2 and cap <= MIB:
                    chk(f'{label}/{arm}: P6 histogram 2 > K/M', hq[1] > K / M, f'({hq[1]} > {K / M:.1f})')
            elif arm == 'defres':
                chk(f'{label}/{arm}: P7 no refusal, no discard', ref == 0 and dm.get('RequestDiscarded') == 0
                    and totals.get('ovl_bytes') == 0)
                W = int(row.get('W', 128))
                chk(f'{label}/{arm}: P7 peak sumA = N W M', r['pa'] == n * W * M, f'({r["pa"]} vs {n * W * M})')
            if arm in ('Bts', 'Btl', 'Bdl', 'Bds') or arm.startswith('n') or arm == 'defres' or arm.startswith('A_'):
                chk(f'{label}/{arm}: P7 global reserve back to 0 (meters RequestsSize delta)',
                    dm.get('RequestsSize') == 0, str(dm.get('RequestsSize')))
        sl = L + '/system.log'
        if os.path.exists(sl):
            txt = open(sl, errors='replace').read()
            n_other = len(re.findall(r'requests/second|spent over|timed out before it could start', txt))
            chk(f'{label}: system.log has no other overload text', n_other == 0, str(n_other))
    print(f'SUMMARY ok={res["ok"]} FAIL={res["FAIL"]}')
    sys.exit(1 if res['FAIL'] else 0)


if __name__ == '__main__':
    main()
