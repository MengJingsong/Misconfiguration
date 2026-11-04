#!/usr/bin/env python3
"""selfcheck.py <run dir, e.g. ~/stage4-logs/sep/run1>: independent self-check of run 1 of
concurrent_writes-takeWorkPermit-workPermits--autonomous (results §5). It does not read summary.txt, unit-analyze's output
or analysis.json. Sources: unit — the per-test logs test-<rep>.log (the test JVM's own log, a different file and format
from the ant log the run script parsed) and the ant logs' "Tests run" lines; cluster — samples-tp.csv, samples-heap.csv,
samples-jmx-<lifetime>.csv, stress-<run>.out, system-<lifetime>.log, session.log (nodetool output), the class histograms,
and phases.json for the time windows only. Prints 'ok' / 'FAIL' per check and a tally."""
import json, math, re, sys
from datetime import datetime, timezone

D = sys.argv[1]
MIB, KIB = 1 << 20, 1 << 10
S = 64 * KIB
T = {'ok': 0, 'FAIL': 0}


def chk(desc, cond):
    T['ok' if cond else 'FAIL'] += 1
    print(f'{"ok  " if cond else "FAIL"} {desc}')
    return cond


def info(s):
    print(f'info {s}')


# ------------------------------------------------------------------ unit tier
KEYS = ['n', 'cap', 'submitted', 'rejected', 'active', 'pending', 'maxPool', 'mei_inline', 'mei_pendingDelta', 'liveDeltaMiB', 'payloadMiB']


def unit_records(path):
    """rebuild the PROBE records from the test JVM's own log: fragments 'PROBE n=', ' cap=', ... each followed by its value"""
    msgs = []
    for l in open(path, errors='replace'):
        m = re.match(r'^INFO\s+\[main\] \S+ (.*)$', l.rstrip('\n'))
        if m:
            msgs.append(m.group(1))
    recs = []
    i = 0
    while i < len(msgs):
        if msgs[i] == 'PROBE n=':
            rec, j, ok = {}, i, True
            for k in KEYS:
                key = msgs[j]
                exp = 'PROBE n=' if k == 'n' else f' {k}='
                if key != exp:
                    ok = False; break
                rec[k] = msgs[j + 1]
                j += 2
            if ok:
                recs.append(rec)
                i = j
                continue
        i += 1
    return recs


def unit():
    reps = {'rep1': 4000, 'rep2': 4000, 'm8000': 8000}
    claim = {}
    for rep, M in reps.items():
        ant = open(f'{D}/unit/ant-{rep}.log', errors='replace').read()
        tr = re.findall(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+)', ant)
        chk(f'unit {rep}: ant reports 3 tests, 0 failures, 0 errors ({tr[:1]}); BUILD SUCCESSFUL', tr and tr[0] == ('3', '0', '0') and 'BUILD SUCCESSFUL' in ant)
        allrecs = unit_records(f'{D}/unit/test-{rep}.log')
        # the per-test log is appended by every ant testsome of this class in the clone (shakedown1, then rep1, rep2,
        # m8000): this rep's records are the last 8
        recs = allrecs[-8:]
        chk(f'unit {rep}: {len(allrecs)} PROBE records in the appended test log; the last 8 are 4 claim + 4 control rows with M = {M} tasks offered '
            f'(claim submitted {[r["submitted"] for r in recs[:4]]})',
            len(recs) == 8 and [r['cap'] for r in recs] == ['0'] * 4 + ['16777216'] * 2 + ['67108864'] * 2
            and all(int(r['submitted']) == M for r in recs[:4]) and all(int(r['submitted']) + int(r['rejected']) == M for r in recs[4:]))
        cl = {int(r['n']): r for r in recs if r['cap'] == '0'}
        claim[rep] = cl
        pay = M * S / MIB
        for n, r in sorted(cl.items()):
            chk(f'unit {rep} N={n}: active {r["active"]} = min(N, M); pending {r["pending"]} = M - N + 1; maxPool {r["maxPool"]}',
                int(r['active']) == min(n, M) and int(r['pending']) == M - n + 1 and int(r['maxPool']) == n)
            chk(f'unit {rep} N={n}: caller-runs refused at line 196 (inline {r["mei_inline"]}, pending +{r["mei_pendingDelta"]})',
                r['mei_inline'] == 'false' and r['mei_pendingDelta'] == '1')
            chk(f'unit {rep} N={n}: liveDelta {r["liveDeltaMiB"]} MiB within 10 % of M x 64 KiB = {pay:.0f} MiB', abs(float(r['liveDeltaMiB']) - pay) <= 0.1 * pay)
        lv = [float(r['liveDeltaMiB']) for r in cl.values()]
        chk(f'unit {rep}: claim liveDelta flat across N (max/min {max(lv) / min(lv):.4f} <= 1.10)', len(lv) == 4 and max(lv) / min(lv) <= 1.10)
        for r in (r for r in recs if r['cap'] != '0'):
            cap = int(r['cap'])
            chk(f'unit {rep} control cap {cap >> 20} MiB N={r["n"]}: submitted {r["submitted"]} = cap / 64 KiB, liveDelta {r["liveDeltaMiB"]} MiB within {4 if cap == 16 * MIB else 8} MiB of the cap',
                int(r['submitted']) == cap // S and abs(float(r['liveDeltaMiB']) - (cap >> 20)) <= (4 if cap == 16 * MIB else 8))
        sup = [l for l in open(f'{D}/unit/test-{rep}.log', errors='replace') if 'SUPPL idle' in l]
        info(f'unit {rep}: {len(sup)} SUPPL fragments in the test log (the run script rebuilt them from the ant log)')
    for n in (0, 2, 32, 128):
        a, b, c = (float(claim[r][n]['liveDeltaMiB']) for r in ('rep1', 'rep2', 'm8000'))
        chk(f'unit N={n}: repeat {a} vs {b} MiB within 10 %; M 8000 / 4000 = {c / ((a + b) / 2):.3f} in [1.8, 2.2]',
            abs(a - b) <= 0.1 * min(a, b) and 1.8 <= c / ((a + b) / 2) <= 2.2)
    # supplementary: rebuild from the ant log of rep1 independently of the run script (SubstituteLogger fragments)
    ant = open(f'{D}/unit/ant-rep1.log', errors='replace').read()
    frag = re.findall(r'\[main\] \S+ SubstituteLogger\.java:\d+ - (.*)', ant)
    text = ''.join(frag)
    sup = re.findall(r'SUPPL idle k=(\d) pendingBefore=(\d+) activeBefore=(\d+) ran=(true|false) mei_inline=(true|false)', text)
    chk(f'unit rep1 SUPPLEMENTARY: 5 idle calls, all ran on a worker and none inline ({sup})',
        len(sup) == 5 and all(s[3] == 'true' and s[4] == 'false' and s[1] == '0' for s in sup))


# ------------------------------------------------------------------ cluster tier
def csv(path):
    lines = open(path).read().splitlines()
    h = lines[0].split(',')
    return [dict(zip(h, l.split(','))) for l in lines[1:] if len(l.split(',')) == len(h)]


def jmx(lt):
    out = []
    for l in open(f'{D}/cluster/samples-jmx-{lt}.csv').read().splitlines()[1:]:
        v = l.split(',')
        try:
            out.append((int(v[0]), float(v[1]), float(v[2]), float(v[3]), float(v[4])))
        except (ValueError, IndexError):
            pass
    return out


def stress(lab):
    t = open(f'{D}/cluster/stress-{lab}.out', errors='replace').read()
    g = lambda p: (re.search(p, t, re.M).group(1).replace(',', '') if re.search(p, t, re.M) else None)
    return {'rate': g(r'^Op rate\s*:\s*([\d,]+) op/s'), 'parts': g(r'^Total partitions\s*:\s*([\d,]+)'),
            'errors': g(r'^Total errors\s*:\s*([\d,]+)'), 'cmd_ok': 'no-warmup' not in t or True, 'text': t}


def utc_ms(s):
    return int(datetime.strptime(s, '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=timezone.utc).timestamp() * 1000)


def linreg(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else float('nan')


def cluster():
    P = {p['run']: p for p in json.load(open(f'{D}/cluster/phases.json'))}
    tp = csv(f'{D}/cluster/samples-tp.csv')
    hp = csv(f'{D}/cluster/samples-heap.csv')
    sess = open(f'{D}/cluster/session.log', errors='replace').read()
    chk('cluster: six runs in phases.json in the order R0, R32, R2, R128, PC0, PC (R2 amendment)', list(P) == ['R0', 'R32', 'R2', 'R128', 'PC0', 'PC'])
    # concurrency read back: every getconcurrency output in session.log, in order
    gc = [int(x) for x in re.findall(r'^MutationStage\s+-?\d+\s+(-?\d+)\s*$', sess, re.M)]
    chk(f'cluster: getconcurrency MaximumPoolSize read back in order 32, 0, 32, 32, 2, 128, 32, 32 ({gc})', gc == [32, 0, 32, 32, 2, 128, 32, 32])
    # the stress commands
    cmds = re.findall(r'\(background\) (tools/bin/cassandra-stress .*)', sess)
    chk(f'cluster: every stress command has no-warmup (R1), 128 threads, 64 KiB values, node 127.0.0.11 ({len(cmds)} commands)',
        len(cmds) == 7 and all('no-warmup' in c and 'threads=128' in c and "size=FIXED(65536)" in c and '-node 127.0.0.11' in c for c in cmds))
    chk('cluster: R32/R2/R128 throttled 400/s, R0/PC0/PC unthrottled', [('throttle=400/s' in c) for c in cmds[1:]] == [False, True, True, True, False, False])
    # R0 ---------------------------------------------------------------
    p = P['R0']
    sl = open(f'{D}/cluster/system-1.log', errors='replace').read()
    rs = re.findall(r'^INFO\s+\[[^\]]+\] (\S+) SEPExecutor\.java:\d+ - Resized MutationStage maximum pool size from (\d+) to (\d+)', sl, re.M)
    chk(f'R0: system.log shows the pool resized 32 -> 0 and 0 -> 32 ({[(a, b) for _, a, b in rs]})', [(a, b) for _, a, b in rs] == [('32', '0'), ('0', '32')])
    if len(rs) == 2:
        t0, t1 = utc_ms(rs[0][0]), utc_ms(rs[1][0])
        chk(f'R0: the resizes are {(t0 - p["stress_start"]) / 1000:.1f} s and {(t1 - p["stress_start"]) / 1000:.1f} s after stress start (≈ 10 and 130 s)',
            8 <= (t0 - p['stress_start']) / 1000 <= 14 and 126 <= (t1 - p['stress_start']) / 1000 <= 135)
        p['set0'], p['set32'] = t0, t1        # use the node's own times from here on
    w_tp = [r for r in tp if r['run'] == 'R0' and p['set0'] <= int(r['t_ms']) <= p['set32']]
    w_hp = [r for r in hp if r['run'] == 'R0' and p['set0'] <= int(r['t_ms']) <= p['set32']]
    base = [r for r in hp if r['run'] == 'R0' and p['base'][0] <= int(r['t_ms']) <= p['base'][1]]
    late = [r for r in w_tp if int(r['t_ms']) > p['set0'] + 5000]
    chk(f'R0: Active = 0 at all {len(late)} tpstats samples after the first 5 s of pool 0', late and all(r['active'] == '0' for r in late))
    pend = [int(r['pending']) for r in w_tp]
    chk(f'R0: Pending never falls in the pool-0 window (samples {pend})', all(b >= a for a, b in zip(pend, pend[1:])))
    xs = [(int(r['t_ms']) - p['set0']) / 1000 for r in w_tp if int(r['t_ms']) <= p['stress_start'] + 120000]
    ys = [int(r['pending']) for r in w_tp if int(r['t_ms']) <= p['stress_start'] + 120000]
    rate = linreg(xs, ys)
    chk(f'R0: Pending grows at {rate:.1f} mutations/s while stress runs (B3c estimate ≈ 64/s; within ±30 %)', 44.8 <= rate <= 83.2)
    st = stress('R0')
    info(f'R0 stress: op rate {st["rate"]}, partitions {st["parts"]}, errors {st["errors"]}; Pending max {max(pend)}')
    # final pending: tpstats after the stress ended but before the restore
    tail = [int(r['pending']) for r in w_tp if int(r['t_ms']) > p['stress_start'] + 122000]
    chk(f'R0: Pending at the restore (after stress ended) {tail} within ±30 % of 7700', tail and 5390 <= tail[-1] <= 10010)
    # queue heap (D2): heap after GC - memtable data size, minus the baseline's
    net = lambda r: int(r['heap_used_after_gc']) - max(0, int(r['memtable_data_size']))
    bnet = sum(net(r) for r in base) / len(base)
    md = [int(r['memtable_data_size']) for r in w_hp]
    chk(f'R0: memtable data size constant in the pool-0 window ({min(md) / MIB:.2f}–{max(md) / MIB:.2f} MiB; B3h)', max(md) - min(md) <= MIB)
    def pend_near(t):
        c = min(w_tp, key=lambda r: abs(int(r['t_ms']) - t))
        return int(c['pending'])
    pts = [(pend_near(int(r['t_ms'])), net(r) - bnet) for r in w_hp]
    info('R0 (Pending, queue heap MiB) per heap sample: ' + ', '.join(f'({a}, {b / MIB:.0f})' for a, b in pts))
    last_p, last_q = pts[-1]
    chk(f'R0: queue heap at the last pool-0 sample {last_q / MIB:.1f} MiB with Pending {last_p} > 256 MiB (B3g row 1, R5)', last_q > 256 * MIB)
    per = last_q / last_p
    sl_fit = linreg([a for a, _ in pts[1:]], [b for _, b in pts[1:]])
    info(f'R0: queue heap per pending mutation {per / KIB:.1f} KiB (last sample), {sl_fit / KIB:.1f} KiB (regression over samples 2..{len(pts)}); the first sample, '
         f'{(w_hp[0]["t_ms"])} ms, is {(int(w_hp[0]["t_ms"]) - p["set0"]) / 1000:.1f} s into pool 0')
    chk(f'R0: B3f "heap ≈ Pending × 65 KiB (±30 %)" — read {per / KIB:.1f} KiB per mutation (expected to MISS: ≈ 2 × 64 KiB)', 0.7 * 65 * KIB <= per <= 1.3 * 65 * KIB)
    chk(f'R0: queue heap per mutation in [1.7, 2.3] × 64 KiB, i.e. value + one copy ({per / S:.2f} ×; the reading behind the missed sub-prediction)', 1.7 <= per / S <= 2.3)
    jr = [r for r in jmx(p['lifetime']) if p['set0'] <= r[0] <= p['set32']]
    rsmax = max(r[1] for r in jr)
    chk(f'R0: RequestsSize max {rsmax / MIB:.3f} MiB over {len(jr)} JMX samples ≤ 8 MiB, i.e. the queue ({last_q / MIB:.0f} MiB) exceeds counted in-flight bytes by > 400 MiB',
        rsmax <= 8 * MIB and last_q - rsmax > 400 * MIB)
    jheap = max(r[2] for r in jr)
    chk(f'R0: JVM heap used (no forced GC) peaked at {jheap / MIB:.0f} MiB < 2048 MiB, no OOM (no hprof, no OutOfMemoryError in system.log)',
        jheap < 2 * 1024 * MIB and 'java.lang.OutOfMemoryError' not in sl)
    # histogram (supplementary)
    h = open(f'{D}/cluster/histo-R0-pool0.txt').read()
    hb = open(f'{D}/cluster/histo-R0-baseline.txt').read()
    def cnt(txt, cls):
        m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+' + re.escape(cls) + r'(\s|$)', txt, re.M)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    mu, cs, bb, bb0 = cnt(h, 'org.apache.cassandra.db.Mutation'), cnt(h, 'org.apache.cassandra.db.Mutation$CachedSerialization'), cnt(h, '[B'), cnt(hb, '[B')
    pn = pend_near(int(p['stress_start']) + 125000)
    chk(f'R0 supplementary histogram: {mu[0]} Mutation and {cs[0]} Mutation$CachedSerialization instances (Pending ≈ {pn})',
        mu[0] == cs[0] and abs(mu[0] - pn) <= 200)
    info(f'R0 histogram: byte[] {bb[1] / MIB:.1f} MiB vs {bb0[1] / MIB:.1f} MiB at baseline: {(bb[1] - bb0[1]) / max(1, mu[0]) / KIB:.1f} KiB per Mutation (includes the memtable)')
    # drain
    after = [r for r in tp if r['run'] == 'R0' and int(r['t_ms']) > p['set32']]
    before = [r for r in tp if r['run'] == 'R0' and int(r['t_ms']) <= p['set32']][-1]
    d_comp = int(after[-1]['completed']) - int(before['completed'])
    d_drop = int(after[-1]['dropped_mutation']) - int(before['dropped_mutation'])
    chk(f'R0 drain: Pending 0 at the first sample after the restore ({after[0]["pending"]}); completed +{d_comp} = 2 × {int(before["pending"])} queued; dropped MUTATION_REQ +{d_drop}',
        after[0]['pending'] == '0' and abs(d_comp - 2 * int(before['pending'])) <= 300 and abs(d_drop - int(before['pending'])) <= 300)
    hp_after = [r for r in hp if r['run'] == 'R0' and int(r['t_ms']) > p['set32'] + 10000]
    chk(f'R0 drain: heap after GC back to {int(hp_after[-1]["heap_used_after_gc"]) / MIB:.1f} MiB (baseline {sum(int(r["heap_used_after_gc"]) for r in base) / len(base) / MIB:.1f} + memtable {int(hp_after[-1]["memtable_data_size"]) / MIB:.1f} + 50)',
        int(hp_after[-1]['heap_used_after_gc']) <= sum(int(r['heap_used_after_gc']) for r in base) / len(base) + 50 * MIB + int(hp_after[-1]['memtable_data_size']))
    # steady runs -------------------------------------------------------
    means = {}
    for lab in ('R2', 'R32', 'R128'):
        q = P[lab]; n = int(lab[1:])
        t = [r for r in tp if r['run'] == lab and q['stress_start'] <= int(r['t_ms']) <= q['stress_end']]
        hh = [int(r['heap_used_after_gc']) for r in hp if r['run'] == lab and q['stress_start'] <= int(r['t_ms']) <= q['stress_end']]
        means[lab] = sum(hh) / len(hh)
        st = stress(lab)
        chk(f'{lab}: {len(t)} tpstats samples, Active max {max(int(r["active"]) for r in t)} ≤ {n}, Pending max {max(int(r["pending"]) for r in t)}; stress {st["rate"]} op/s, {st["errors"]} errors',
            max(int(r['active']) for r in t) <= n and st['errors'] == '0' and 380 <= int(st['rate']) <= 420)
        info(f'{lab}: heap after GC mean {means[lab] / MIB:.1f} MiB over {len(hh)} samples (max {max(hh) / MIB:.1f})')
    m = means
    chk(f'R2/R32/R128: heap means {m["R2"] / MIB:.1f} / {m["R32"] / MIB:.1f} / {m["R128"] / MIB:.1f} MiB within 20 % (max/min {max(m.values()) / min(m.values()):.3f}) and not rising with N (R4)',
        max(m.values()) / min(m.values()) <= 1.2 and not (m['R2'] < m['R32'] < m['R128'] and m['R128'] > 1.2 * m['R2']))
    # positive control ----------------------------------------------------
    rsx = {}
    for lab in ('PC0', 'PC'):
        q = P[lab]
        jr = [r for r in jmx(q['lifetime']) if q['stress_start'] <= r[0] <= q['stress_end']]
        rsx[lab] = (max(r[1] for r in jr), sum(r[1] for r in jr) / len(jr), int(stress(lab)['rate']))
        info(f'{lab}: RequestsSize max {rsx[lab][0] / MIB:.2f} MiB, mean {rsx[lab][1] / MIB:.2f} MiB over {len(jr)} samples; op rate {rsx[lab][2]}')
    yaml_pc = re.findall(r'start lifetime 6 \(PC\): [^\n]*', sess)
    chk(f'PC yaml: receive queue 0B (D1) and per-IP 4MiB ({yaml_pc[:1]})', yaml_pc and 'native_transport_receive_queue_capacity=0B' in yaml_pc[0] and 'per_ip=4MiB' in yaml_pc[0])
    chk(f'PC: RequestsSize max {rsx["PC"][0] / MIB:.2f} MiB ≤ 4 MiB while PC0 reaches {rsx["PC0"][0] / MIB:.2f} MiB > 4 MiB (the per-IP cap binds on the counter)',
        rsx['PC'][0] <= 4 * MIB < rsx['PC0'][0])
    chk(f'PC: op rate {rsx["PC"][2]} < PC0 {rsx["PC0"][2]} (B3f; a {100 * (1 - rsx["PC"][2] / rsx["PC0"][2]):.1f} % drop)', rsx['PC'][2] < rsx['PC0'][2])
    # environment
    jv = re.findall(r'^\[[^\]]+\] jvm: (.*)$', sess, re.M)
    chk(f'cluster: every lifetime ran with -Xmx2G, G1 and JMX port 7211 ({len(jv)} lifetimes)', len(jv) == 6 and all('-Xmx2G' in j and 'UseG1GC' in j and 'port=7211' in j for j in jv))
    sl_all = ''.join(open(f'{D}/cluster/system-{i}.log', errors='replace').read() for i in range(6, 7))
    chk('cluster: 127.0.0.11 is the node address in system.log (E1)', '/127.0.0.11' in sl_all or '127.0.0.11:' in sl_all)


unit()
cluster()
print(f'selfcheck: {T["ok"]} ok, {T["FAIL"]} FAIL')
