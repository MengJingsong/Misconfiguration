#!/usr/bin/env python3
"""Independent self-check of run 1, internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.

Re-parses the raw files of ~/stage4-logs/rqc/run1/<label>/ (the trace rqc.trace written by R's Byteman rules, each arm's
writer key logs keys-*.csv, the inbound-table samples vt-*.csv, the JMX polls jmx-*.csv, the class histograms histo-*.txt,
the thread dumps threads-*.txt, and the JMX counter lines in session.log) without importing or reusing cluster-run.py, and
judges the frozen section 9a prediction (hash 5ef01c26...) from its own numbers. Windows come from the key logs (first
send to last completion), not from the run script's arms.csv; arms.csv is only compared against at the end.

usage: selfcheck.py [<run1 log folder>]     prints one line per check ("ok" / "FAIL") and a summary; exit 1 on a FAIL.
"""
import csv, glob, os, re, statistics, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/rqc/run1')
MIB = 1 << 20
ADDR = {'S1': '127.0.0.3', 'S2': '127.0.0.4', 'S3': '127.0.0.5', 'S4': '127.0.0.6'}
# frozen 9a design, written out again from the case file (not read from the harness)
DESIGN = {
    'c512k': (524288, MIB, MIB, {'B': (['S1'], 262144, True)}),
    'c1m': (MIB, MIB, MIB, {'B': (['S1'], 262144, True), 'nohold': (['S1'], 262144, False)}),
    'c4m': (4 * MIB, MIB, MIB, {'B': (['S1'], 262144, True), 'p2': (['S1', 'S2'], 262144, True),
                                'p4': (['S1', 'S2', 'S3', 'S4'], 262144, True), 'small': (['S1'], 32768, True)}),
    'c16m': (16 * MIB, MIB, MIB, {'B': (['S1'], 262144, True)}),
    'defres': (4 * MIB, 128 * MIB, 512 * MIB, {'B': (['S1'], 262144, True)}),
}
PRED_N = {'c512k': 5, 'c1m': 7, 'c4m': 19, 'c16m': 67}       # 9a: n = floor((C + 1 MiB) / M) = 5 · 7 · 19 · 67
PRED_NS = 159                                               # 9a: small arm n_s

results = []


def check(name, ok, detail):
    results.append((name, bool(ok)))
    print(f'{"ok  " if ok else "FAIL"} {name}: {detail}')


LINE = re.compile(r'^(acq|rel|hold) (.*) ms=(\d+)$')
KV = re.compile(r'(\w+)=(\S+)')


def parse_trace(path):
    ev = []
    for raw in open(path, errors='replace'):
        m = LINE.match(raw.rstrip('\n'))
        if not m:
            continue
        kind, body, ms = m.group(1), m.group(2), int(m.group(3))
        d = dict(KV.findall(body))
        d['kind'], d['ms'] = kind, ms
        if kind != 'hold':
            d['b'], d['q'] = int(d['b']), int(d['q'])
            hid = d['id']
            t = re.search(r'-(URGENT|SMALL|LARGE|LEGACY)_MESSAGES-', hid)
            # an id without a connection type is a CQL client connection on R (CQLMessageHandler, the same
            # AbstractMessageHandler): the samplers' reads of system_views; out of scope, kept as "other"
            d['peer'] = hid.split('->')[0] if t else 'cql-client'
            d['type'] = t.group(1) + '_MESSAGES' if t else 'CQL'
        if kind == 'acq':
            d['cap'] = int(d['cap'])
            d['epu'], d['epl'] = (int(x) for x in d['ep'].split('/'))
            d['glu'], d['gll'] = (int(x) for x in d['gl'].split('/'))
        ev.append(d)
    return ev


def keylog(path):
    rows = [l.strip().split(',') for l in open(path) if l.strip()]
    return [(int(r[0]), int(r[1]), int(r[2]), r[3]) for r in rows]


def vt(path):
    out = []
    if not os.path.exists(path):
        return out
    for r in csv.DictReader(open(path)):
        if r['address'] in ('ERROR', None) or not r['ms'].isdigit():
            continue
        out.append({k: (v if k == 'address' else int(v)) for k, v in r.items()})
    return out


def last_by_addr(rows):
    if not rows:
        return {}
    t = max(r['ms'] for r in rows)
    return {r['address']: r for r in rows if r['ms'] == t}


def jmxcsv(path):
    out = []
    for l in open(path):
        p = l.strip().split(',')
        if len(p) == 4 and all(x.lstrip('-').isdigit() for x in p):
            out.append(tuple(int(x) for x in p))
    return out


def mutations(path):
    txt = open(path).read()
    m = re.search(r'^\s*\d+:\s+(\d+)\s+\d+\s+org\.apache\.cassandra\.db\.Mutation\s*(\(.*)?$', txt, re.M)
    return int(m.group(1)) if m else 0


def held_threads(path):
    n = 0
    for blk in open(path).read().split('\n\n'):
        if blk.startswith('"MutationStage') and 'MutationVerbHandler.doVerb' in blk and 'Thread.sleep' in blk:
            n += 1
    return n


def session_counters(label):
    """JMX counter lines of session.log, in order: per arm R table+drop, S1-S4 drop+hints (before), the same (after)."""
    seq = []
    for l in open(f'{ROOT}/{label}/session.log', errors='replace'):
        m = re.match(r'^org\.apache\.cassandra\.metrics:type=(Table,keyspace=ks,scope=t,name=WriteLatency|DroppedMessage,'
                     r'scope=MUTATION,name=Dropped|Storage,name=TotalHints)\|Count\|(\d+)$', l.strip())
        if m:
            seq.append((m.group(1).split(',')[0], int(m.group(2))))
    return seq


summary_rows = {}
for label, (C, E, G, arms) in DESIGN.items():
    tpath = f'{ROOT}/{label}/rqc.trace'
    if not os.path.exists(tpath):
        check(f'{label}: trace present', False, tpath)
        continue
    ev = parse_trace(tpath)
    acq = [e for e in ev if e['kind'] == 'acq']
    first = acq[0]
    check(f'{label}: read-back (first acq line)', first['cap'] == C and first['epl'] == E and first['gll'] == G,
          f"cap {first['cap']} ep {first['epl']} gl {first['gll']} vs {C} {E} {G}")
    cnt = session_counters(label)
    # per arm, 5 drop lines + 1 table line + 4 hint lines before, the same after = 20 lines in a fixed order
    per_arm = []
    i = 0
    while i < len(cnt):
        per_arm.append(cnt[i:i + 20])
        i += 20
    order = [a for a in arms if os.path.isdir(f'{ROOT}/{label}/{a}')]
    for k, arm in enumerate(order):
        senders, payload, hold = arms[arm]
        D = f'{ROOT}/{label}/{arm}'
        tag = f'{label}/{arm}'
        keysB = {s: keylog(f'{D}/keys-{s}.csv') for s in senders}
        keysA = keylog(f'{D}/keys-A.csv')
        t0 = min(r[1] for v in keysB.values() for r in v)
        t_last_send = max(r[1] for v in keysB.values() for r in v)
        t_last_done = max(r[2] for v in keysB.values() for r in v)
        drain = [r for r in vt(f'{D}/vt-drain.csv')]
        zero_ms = sorted({r['ms'] for r in drain if all(x['using_bytes'] == 0 for x in drain if x['ms'] == r['ms'])})
        t_end = zero_ms[0] if zero_ms else t_last_done + 5000
        win = [e for e in ev if t0 - 2000 <= e['ms'] <= t_end]     # 2 s before the first send: the writers' connect
        dtype = 'LARGE_MESSAGES' if payload == 262144 else 'SMALL_MESSAGES'
        wp = {'/' + ADDR[s] + ':7010' for s in senders}
        wa = [e for e in win if e['kind'] == 'acq']
        da = [e for e in wa if e['type'] == dtype and e['peer'] in wp]
        sizes = sorted(e['b'] for e in da if e['b'] > payload)
        M = statistics.median(sizes)
        ok_s = [e for e in da if e['out'] == 'SUCCESS']
        ref = [e for e in da if e['out'] != 'SUCCESS']
        peaks = {}
        for e in ok_s:
            peaks[e['peer']] = max(peaks.get(e['peer'], 0), e['q'])
        peak = max(peaks.values())
        others = [e for e in wa if not (e['type'] == dtype and e['peer'] in wp)]
        # exact per-line rules
        inter = [e for e in wa if e['type'] != 'CQL']
        bad_succ = [e for e in inter if e['out'] == 'SUCCESS' and e['q'] > e['cap'] + E]
        bad_gl = [e for e in wa if e['glu'] > e['gll'] or e['epu'] > e['epl']]
        ncql = len(wa) - len(inter)
        glmax = max([e['glu'] for e in wa if e['gll'] == G] + [0])
        # node total rebuilt from the trace (last printed q per handler id), and the print-order diagnostic
        last, tot, prev, disorder = {}, 0, {}, 0
        for e in win:
            if e['kind'] == 'hold':
                continue
            if e['kind'] == 'rel' and prev.get(e['id'], ('',))[0] == 'rel' and e['q'] > prev[e['id']][1]:
                disorder += 1
            prev[e['id']] = (e['kind'], e['q'])
            last[e['id']] = e['q']
            tot = max(tot, sum(last.values()))
        vB = vt(f'{D}/vt-B.csv')
        sums = {}
        for r in vB:
            sums[r['ms']] = sums.get(r['ms'], 0) + r['using_bytes']
        vt_tot = max(sums.values()) if sums else 0
        v0, v1 = last_by_addr(vt(f'{D}/vt-before.csv')), last_by_addr(vt(f'{D}/vt-after.csv'))
        thr = {s: v1[ADDR[s]]['throttled_count'] - v0[ADDR[s]]['throttled_count'] for s in senders}
        thn = {s: v1[ADDR[s]]['throttled_nanos'] - v0[ADDR[s]]['throttled_nanos'] for s in senders}
        expired = sum(v1[a]['expired_count'] - v0[a]['expired_count'] for a in v1 if a in v0)
        # rows and outcomes from the key logs
        nrows = len(keysA) + sum(len(v) for v in keysB.values())
        nerr = sum(1 for r in keysA if r[3] != 'ok') + sum(1 for v in keysB.values() for r in v if r[3] != 'ok')
        # counters from session.log
        blk = per_arm[k] if k < len(per_arm) else []
        def val(i):
            return blk[i][1] if i < len(blk) else None
        # order inside a block: R table, R drop, S1 drop, S1 hints, ... S4 drop, S4 hints (before), then the same (after)
        names = [x[0] for x in blk]
        try:
            writes = val(10) - val(0)
            rdrop = val(11) - val(1)
            sdrop = sum(val(12 + 2 * j) - val(2 + 2 * j) for j in range(4))
            shint = sum(val(13 + 2 * j) - val(3 + 2 * j) for j in range(4))
            cnt_ok = names[0] == 'Table' and names[10] == 'Table'
        except (TypeError, IndexError):
            writes = rdrop = sdrop = shint = None
            cnt_ok = False
        # real resource
        idle = mutations(f'{D}/histo-idle.txt')
        m1, m2 = mutations(f'{D}/histo-b1.txt') - idle, mutations(f'{D}/histo-b2.txt') - idle
        h1, h2 = held_threads(f'{D}/threads-b1.txt'), held_threads(f'{D}/threads-b2.txt')
        jc, jb = jmxcsv(f'{D}/jmx-ctrl.csv'), jmxcsv(f'{D}/jmx-B.csv')
        idle_pool = statistics.mean(r[1] for r in jc)
        t_cap = min(e['ms'] for e in ref) if ref else t0
        cap_s = [r for r in jb if t_cap <= r[0] <= t_last_send]
        pool_mean = statistics.mean(r[1] for r in cap_s) - idle_pool if cap_s else None
        th = max(1, len(cap_s) // 3)
        drift = statistics.mean(r[1] for r in cap_s[-th:]) - statistics.mean(r[1] for r in cap_s[:th]) if len(cap_s) >= 3 else None
        holds = sum(1 for e in win if e['kind'] == 'hold')
        A0, A1 = min(r[1] for r in keysA), max(r[2] for r in keysA)
        a_ref = sum(1 for e in ev if e['kind'] == 'acq' and A0 <= e['ms'] <= A1 and e['out'] != 'SUCCESS')
        summary_rows[tag] = dict(M=M, peak=peak, peaks=peaks, n=round(peak / M, 3), ref=len(ref),
                                 outs=sorted({e['out'] for e in ref}), glmax=glmax, tot=tot, vt_tot=vt_tot, disorder=disorder,
                                 thr=thr, m1=m1, m2=m2, h1=h1, h2=h2, pool=pool_mean, drift=drift, rows=nrows, err=nerr,
                                 writes=writes, rdrop=rdrop, sdrop=sdrop, shint=shint, expired=expired, holds=holds)
        print(f'---- {tag}: {summary_rows[tag]}')

        # validity and rules, every arm
        check(f'{tag}: counter lines parsed (20 per arm)', cnt_ok and len(blk) == 20, f'{len(blk)} lines {names[:2]}')
        if hold:
            check(f'{tag}: hold fired', holds > 0 and h1 > 0, f'hold lines {holds}, held threads b1 {h1} b2 {h2}')
        check(f'{tag}: A took no refusal', a_ref == 0, f'{a_ref} refusals in A')
        check(f'{tag}: every SUCCESS q <= cap + E; reserves within limits', not bad_succ and not bad_gl,
              f'{len(bad_succ)} / {len(bad_gl)} violations of {len(inter)} internode acq lines ({ncql} CQL-client lines)')
        nodrop = nerr == 0 and writes == nrows and rdrop == 0 and expired == 0 and sdrop == 0 and shint == 0
        if hold:
            check(f'{tag}: no write lost', nodrop, f'errors {nerr}, R writes {writes} vs rows {nrows}, R drops {rdrop}, '
                  f'expired {expired}, sender drops {sdrop}, sender hints {shint}')
        else:
            print(f'info {tag}: unheld control no-drop reading: errors {nerr}, R writes {writes} vs rows {nrows}, R drops '
                  f'{rdrop}, expired {expired}, sender drops {sdrop}, sender hints {shint}')
        low = E == MIB and G == MIB
        if low and hold and len(senders) == 1:
            n = PRED_N.get(label) if payload == 262144 else PRED_NS
            check(f'{tag}: plateau n·M with n = {n}', C + E - max(sizes) < peak <= C + E and round(peak / M) == n
                  and int((C + E) // max(sizes)) == int((C + E) // min(sizes)) == n,
                  f'peak {peak} = {peak / M:.3f} M, interval ({C + E - max(sizes)}, {C + E}], M {min(sizes)}..{max(sizes)}')
            check(f'{tag}: refusals all INSUFFICIENT_GLOBAL, throttled count and nanos rose',
                  ref and {e['out'] for e in ref} == {'INSUFFICIENT_GLOBAL'} and all(thr[s] > 0 and thn[s] > 0 for s in senders),
                  f'{len(ref)} refusals {sorted({e["out"] for e in ref})}, throttled {thr}')
            check(f'{tag}: other handlers <= C, no refusal', max([e['q'] for e in others] + [0]) <= C
                  and not [e for e in others if e['out'] != 'SUCCESS'], f'max q {max([e["q"] for e in others] + [0])}')
            if payload == 262144:
                x = min(n, 32)
                check(f'{tag}: live Mutation above idle min(n,32)={x} (-3/+2), b1~b2 within 3',
                      x - 3 <= m1 <= x + 2 and x - 3 <= m2 <= x + 2 and abs(m1 - m2) <= 3, f'{m1}, {m2}')
                if n > 32:
                    fr = (n - 32) * M
                    check(f'{tag}: pool above idle within x2 of (n-32)·M = {fr:.0f}', fr / 2 <= pool_mean <= 2 * fr, f'{pool_mean:.0f}')
                else:
                    check(f'{tag}: pool above idle < 2 MiB', pool_mean < 2 * MIB, f'{pool_mean:.0f}')
                check(f'{tag}: pool flat while S is capped (drift < M)', drift < M, f'drift {drift:.0f}, M {M}')
            else:
                check(f'{tag}: live Mutation above idle n_s={n} (-4/+2), b1~b2 within 3',
                      n - 4 <= m1 <= n + 2 and n - 4 <= m2 <= n + 2 and abs(m1 - m2) <= 3, f'{m1}, {m2}')
        if low and hold and len(senders) > 1:
            P = len(senders)
            fl = int(C // min(sizes)) * min(sizes)
            check(f'{tag}: each peer in [floor(C/M)·M, C+E]', all(fl <= peaks.get('/' + ADDR[s] + ':7010', 0) <= C + E for s in senders),
                  f'{peaks}')
            check(f'{tag}: global in use peak in (G - M, G]', G - max(sizes) < glmax <= G, f'{glmax}')
            check(f'{tag}: node total (trace rebuild) <= P·C + G + 64 KiB and sum of peaks >= P·floor(C/M)·M',
                  tot <= P * C + G + 65536 and sum(peaks.values()) >= P * fl,
                  f'rebuild {tot} vs {P * C + G + 65536}; peaks sum {sum(peaks.values())} vs {P * fl}; '
                  f'(diagnostic: rel pairs out of order {disorder}, sampled using_bytes total max {vt_tot})')
            check(f'{tag}: refusals and every peer throttled', ref and all(thr[s] > 0 for s in senders), f'{thr}')
        if not low:
            check(f'{tag}: default reserves: no refusal, no throttle, peak in (C + 1 MiB, W·M]',
                  not ref and all(thr[s] == 0 for s in senders) and C + MIB < peak <= 128 * max(sizes),
                  f'{len(ref)} refusals, throttled {thr}, peak {peak}')

# the peer sweep at 4 MiB: node totals linear in P with slope C
sweep = [(t, len(DESIGN['c4m'][3][t.split('/')[1]][0]), summary_rows[t]) for t in ('c4m/B', 'c4m/p2', 'c4m/p4') if t in summary_rows]
if len(sweep) == 3:
    print('---- peer sweep at 4 MiB: ' + '; '.join(f'P={p}: sum of peaks {sum(r["peaks"].values())}, sampled total max '
                                                 f'{r["vt_tot"]}, rebuild {r["tot"]}' for _, p, r in sweep))
# the capacity sweep: the plateau follows C
cs = [(t, summary_rows[t]['peak']) for t in ('c512k/B', 'c1m/B', 'c4m/B', 'c16m/B') if t in summary_rows]
check('capacity sweep: plateau strictly increasing with C', len(cs) == 4 and all(cs[i][1] < cs[i + 1][1] for i in range(3)),
      f'{cs}')

# agreement with the run script's arms.csv
for label in DESIGN:
    p = f'{ROOT}/{label}/arms.csv'
    if not os.path.exists(p):
        continue
    for r in csv.DictReader(open(p)):
        tag = r['arm']
        if tag not in summary_rows:
            continue
        s = summary_rows[tag]
        same = (int(r['data_peak']) == s['peak'] and int(r['refusals']) == s['ref'] and int(r['gl_max']) == s['glmax']
                and int(r['writes_R']) == s['writes'] and int(r['rows']) == s['rows'])
        check(f'{tag}: run script agrees (peak, refusals, global max, R writes, rows)', same,
              f"script {r['data_peak']} {r['refusals']} {r['gl_max']} {r['writes_R']} {r['rows']} / self {s['peak']} "
              f"{s['ref']} {s['glmax']} {s['writes']} {s['rows']}")

nf = sum(1 for _, ok in results if not ok)
print(f'SELFCHECK {len(results)} checks, {len(results) - nf} ok, {nf} FAIL')
sys.exit(1 if nf else 0)
