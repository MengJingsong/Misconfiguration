#!/usr/bin/env python3
"""Independent self-check of run 1, SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS
(results §5). Re-parses the raw files, not summary.txt or the run script's EXPECTED lines:
  unit:     <logs>/unit/harness.out          the recorder's "STAGE4 line" lines and "STAGE4 deep" lines
  cluster:  <logs>/<label>/mat.trace         the Byteman lines (mat-trace.btm, hold.btm)
            <logs>/<label>/session.log       the client's JSON lines (query.py output: rows, bad, start_ms, end_ms per query)
            <logs>/<label>/histo-*.txt       the raw jcmd GC.class_histogram output (mtime = end of the jcmd)
            <logs>/<label>/trace-events-*.txt, jvm-args.txt, session.log's VM.system_properties output
Each client call is matched to the trace lines between its first query's start and its last query's end (+ 2 s), and every §9a
relation is recomputed from those. usage: selfcheck.py [<logs dir>, default ~/stage4-logs/mmk/run1]. Prints one line per check
and a total; exit 1 if any check fails."""
import glob, json, os, re, sys

LOGS = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/mmk/run1')
Q, K, N_T, N_FAR, M_FAR = 8, 10, 200000, 50000, 16001
LABELS = {'1000': 1000, '4000': 4000, 'default': 16000, '64000': 64000, '0': 0, '2147483647': 2147483647}
SPK = 'org.apache.cassandra.index.sai.utils.PrimaryKey$Factory$SkinnyPrimaryKey'
BDK = 'org.apache.cassandra.db.BufferDecoratedKey'
FIVE = [SPK, BDK, 'org.apache.cassandra.dht.Murmur3Partitioner$LongToken', 'java.nio.HeapByteBuffer', '[B']
res = []


def ok(name, cond, detail=''):
    res.append(bool(cond))
    print(f'{"ok  " if cond else "FAIL"} {name}  {detail}')


def within(got, want):
    return got is not None and abs(got - want) <= 0.01 * want + 100


def fld(line, name):
    m = re.search(r'\b' + name + r'=(-?\d+|null)\b', line)
    return None if not m or m.group(1) == 'null' else int(m.group(1))


def ms(line):
    m = re.search(r' ms=(\d+)$', line)
    return int(m.group(1)) if m else None


# ------------------------------------------------------------------ unit tier
def unit():
    p = f'{LOGS}/unit/harness.out'
    lines = open(p).read().splitlines()
    by = {}
    for l in lines:
        m = re.match(r'STAGE4 line (U\d \S+(?: \S+)? L=\S+ M=\d+) (.*)$', l)
        if m:
            by.setdefault(m.group(1), []).append(m.group(2))
    for tag, ls in sorted(by.items()):
        mL = re.search(r'L=(\d+|MAX)', tag); mM = re.search(r'M=(\d+)', tag)
        L = 2 ** 31 - 1 if mL.group(1) == 'MAX' else int(mL.group(1)); M = int(mM.group(1))
        ref = [x for x in ls if x.startswith('mat refuse')]; ex = [x for x in ls if x.startswith('mat exit')]
        ann = [x for x in ls if x.startswith('ann ')]; hyb = [x for x in ls if x.startswith('hybrid ')]
        if M <= L:
            good = not ref and len(ex) == 1 and fld(ex[0], 'returned') == M and len(hyb) == 1 and fld(hyb[0], 'size') == M and not ann
        else:
            w = max(L + 1, 1)
            good = (len(ref) == 1 and fld(ref[0], 'size') == w and fld(ref[0], 'count') == w and len(ex) == 1
                    and 'returned=null' in ex[0] and len(ann) == 1 and not hyb)
        ok(f'unit {tag}: {"allow, list = M" if M <= L else "refuse at L + 1, then ANN plan"}', good,
           f'refuse={[fld(x, "size") for x in ref]} exit={[x.split("returned=")[1].split()[0] for x in ex]} ann={len(ann)} hybrid={[fld(x, "size") for x in hyb]}')
        if tag.startswith('U4'):
            caps = [fld(x, 'cap') for x in ls if x.startswith('pairs')]
            ok('unit U4: four pairs caps >= 3950', len(caps) == 4 and min(caps) >= 3950, f'caps={caps}')
        if tag.startswith('U5'):
            pr = [fld(x, 'processed') for x in ls if x.startswith('processed=')]
            if M > L:
                ok(f'unit {tag}: processed >= 0.9 x 1899 = 1709', len(pr) == 1 and pr[0] >= 1709, f'processed={pr}')
            else:
                ok(f'unit {tag}: processed <= 10', len(pr) == 1 and pr[0] <= 10, f'processed={pr}')
    deep = {int(m.group(1)): int(m.group(2)) for m in (re.match(r'STAGE4 deep L=(\d+) keys=\d+ bytes=(\d+)', l) for l in lines) if m}
    ls_ = sorted(deep)
    slopes = [(deep[b] - deep[a]) / (b - a) for a, b in ((ls_[0], ls_[1]), (ls_[1], ls_[2]), (ls_[0], ls_[2]))]
    ok('unit U2: every slope b in 120..200 B/key', all(120 <= s <= 200 for s in slopes), f'b={[round(s, 2) for s in slopes]}')
    ok('unit U2: slopes within 2 %', max(slopes) <= 1.02 * min(slopes), f'ratio={max(slopes) / min(slopes):.4f}')
    return sum(slopes[:2]) / 2


# ------------------------------------------------------------------ cluster tier
def histo_raw(path):
    v = {}
    for l in open(path):
        p = l.split()
        if len(p) >= 4 and p[0].endswith(':') and p[3] in FIVE:
            v[p[3]] = (int(p[1]), int(p[2]))
    return v, int(os.path.getmtime(path) * 1000)


def clients(label):
    """the query.py result lines in order. cluster-run.py logs at most 4,000 characters of a line, which cuts a traced query's
    trace_events; "queries" precedes them in the JSON, so it is recovered from the cut line"""
    out = []
    for l in open(f'{LOGS}/{label}/session.log', errors='replace'):
        if l.startswith('OK {') or l.startswith('ERR {'):
            body = l.split(' ', 1)[1].strip()
            try:
                b = json.loads(body)
            except ValueError:
                m = re.search(r'"cql": "(.*?)", "protocol": \d+, "queries": (\[.*?\])(?:, "trace_events"|, "secs")', body)
                if not m:
                    continue
                b = {'cql': m.group(1), 'queries': json.loads(m.group(2)), 'cut': True}
            if 'queries' in b:
                b['ok'] = l.startswith('OK ')
                out.append(b)
    for i, b in enumerate(out):     # a call's trace lines run from its first start to the next call's first start
        b['t0'] = min(q['start_ms'] for q in b['queries']) - 50
        b['t1'] = (min(q['start_ms'] for q in out[i + 1]['queries']) - 51) if i + 1 < len(out) else 10 ** 15
    return out


def window(trace, c):
    return [l for l in trace if ms(l) is not None and c['t0'] <= ms(l) <= c['t1']]


def kinds(w):
    return {k: [l for l in w if l.startswith(p)] for k, p in
            (('refuse', 'mat refuse'), ('exit', 'mat exit'), ('ann', 'ann '), ('hybrid', 'hybrid '), ('pairs', 'pairs '),
             ('proc', 'processed='), ('hs', 'hold start'), ('he', 'hold end'))}


def rows_ok(c, m, ann_only=False):
    return all(q.get('rows') == K and (ann_only or (q.get('bad') == 0 and (q.get('max_i') or 0) <= m)) for q in c['queries'])


def held_delta(label, tag, w, idle, idle_ms):
    f = f'{LOGS}/{label}/histo-{tag}.txt'
    v, t = histo_raw(f)
    k = kinds(w)
    hs = sorted(ms(x) for x in k['hs']); he = sorted(ms(x) for x in k['he'])
    ok(f'{label} {tag}: histogram taken while all {Q} held (last start < jcmd end < first end)',
       len(hs) == Q and len(he) == Q and hs[-1] < t < he[0], f'starts={len(hs)} ends={len(he)} jcmd_end-last_start={t - hs[-1] if hs else None} ms')
    return {c: v.get(c, (0, 0))[0] - idle.get(c, (0, 0))[0] for c in FIVE}, \
        sum(v.get(c, (0, 0))[1] - idle.get(c, (0, 0))[1] for c in FIVE)


def bytes_check(label, tag, db, n, b_unit):
    bpk = db / n if n else 0
    ok(f'{label} {tag}: five-class bytes change = keys x b (U2 b = {b_unit:.1f}) within 10 %', abs(bpk - b_unit) <= 0.10 * b_unit,
       f'{db:+d} B / {n} keys = {bpk:.1f} B/key')


def check_refuse(label, tag, k, L, n=1):
    w = max(L + 1, 1)
    ok(f'{label} {tag}: {n} refusal(s) at size = count = {w}, list null, {n} ann, no hybrid',
       [fld(x, 'size') for x in k['refuse']] == [w] * n and [fld(x, 'count') for x in k['refuse']] == [w] * n
       and len(k['exit']) == n and all('returned=null' in x for x in k['exit']) and len(k['ann']) == n and not k['hybrid'],
       f'refuse={[fld(x, "size") for x in k["refuse"]]} exit={len(k["exit"])} ann={len(k["ann"])} hybrid={len(k["hybrid"])}')


def check_allow(label, tag, k, m, n=1):
    ok(f'{label} {tag}: {n} list(s) of {m}, hybrid size {m}, no refusal, no ann',
       not k['refuse'] and [fld(x, 'returned') for x in k['exit']] == [m] * n and [fld(x, 'size') for x in k['hybrid']] == [m] * n
       and not k['ann'], f'exit={[fld(x, "returned") for x in k["exit"]]} hybrid={[fld(x, "size") for x in k["hybrid"]]} ann={len(k["ann"])}')


def cluster(b_unit):
    held = {}
    for label, L in LABELS.items():
        d = f'{LOGS}/{label}'
        if not os.path.isdir(d):
            ok(f'{label}: logs present', False); continue
        trace = open(f'{d}/mat.trace').read().splitlines()
        args = open(f'{d}/jvm-args.txt').read().split('\n')
        prop = [a for a in args if 'max_materialized_keys' in a]
        ok(f'{label}: JVM property', prop == ([] if L == 16000 else [f'-Dcassandra.sai.vector_search.max_materialized_keys={L}']), str(prop))
        sl = open(f'{d}/session.log', errors='replace').read()
        # the raw jcmd VM.system_properties output only (cluster-run.py's own note line also carries the text)
        m = re.search(r'^cassandra\.sai\.vector_search\.max_materialized_keys=(\S+)$', sl, re.M)
        ok(f'{label}: VM.system_properties read-back', (m.group(1) if m else None) == (None if L == 16000 else str(L)), m.group(0) if m else 'absent')
        lim = [l for l in trace if l.startswith('limit=')]
        ok(f'{label}: one start-up limit line = {L}', len(lim) == 1 and fld(lim[0], 'limit') == L, str(lim))
        cs = clients(label)
        c = cs.pop(0)
        k = kinds(window(trace, c))
        ok(f'{label} control: ANN-only, 10 rows, no mat line, one ann', 'WHERE' not in c['cql'] and rows_ok(c, 0, True)
           and not k['exit'] and not k['refuse'] and len(k['ann']) == 1, f'exit={len(k["exit"])} ann={len(k["ann"])}')
        idle, idle_ms = histo_raw(f'{d}/histo-idle.txt')
        ok(f'{label}: idle histogram SkinnyPrimaryKey small', idle.get(SPK, (0, 0))[0] < 1000, str(idle.get(SPK)))
        if L == 0:
            c = cs.pop(0); k = kinds(window(trace, c))
            ok(f'{label} C1 single: rows', rows_ok(c, 5)); check_refuse(label, 'C1 single M=5', k, 0)
            continue
        if L == 2 ** 31 - 1:
            c = cs.pop(0); k = kinds(window(trace, c))
            ok(f'{label} C1 single: rows', rows_ok(c, N_T)); check_allow(label, f'C1 single M={N_T}', k, N_T)
            c = cs.pop(0); w = window(trace, c); k = kinds(w)
            ok(f'{label} C1 held: rows', c['ok'] and rows_ok(c, N_T)); check_allow(label, 'C1 held', k, N_T, Q)
            dd, db = held_delta(label, 'C1_held', w, idle, idle_ms)
            bytes_check(label, 'C1 held', db, dd[SPK], b_unit)
            ok(f'{label} C1 held: SkinnyPrimaryKey change = Q x M = {Q * N_T} (1 % + 100)', within(dd[SPK], Q * N_T), f'{dd[SPK]:+d}')
            ok(f'{label} C1 held: BufferDecoratedKey change = Q x M', within(dd[BDK], Q * N_T), f'{dd[BDK]:+d}')
            continue
        # A single
        c = cs.pop(0); k = kinds(window(trace, c))
        ok(f'{label} A single: rows i <= {L}', rows_ok(c, L)); check_allow(label, f'A single M={L}', k, L)
        caps = [fld(x, 'cap') for x in k['pairs']]
        ok(f'{label} A single: 4 pairs caps >= {L - 50}', len(caps) == 4 and min(caps) >= L - 50, f'caps={caps}')
        # A held
        c = cs.pop(0); w = window(trace, c); k = kinds(w)
        ok(f'{label} A held: 8 x rows', c['ok'] and len(c['queries']) == Q and rows_ok(c, L)); check_allow(label, 'A held', k, L, Q)
        dd, db = held_delta(label, 'A_held', w, idle, idle_ms)
        ok(f'{label} A held: SkinnyPrimaryKey change = Q x L = {Q * L}', within(dd[SPK], Q * L), f'{dd[SPK]:+d}')
        bytes_check(label, 'A held', db, dd[SPK], b_unit)
        ok(f'{label} A held: BufferDecoratedKey change = Q x L', within(dd[BDK], Q * L), f'{dd[BDK]:+d}')
        # B traced
        c = cs.pop(0); k = kinds(window(trace, c))
        ok(f'{label} B traced: rows i <= {L + 1}', rows_ok(c, L + 1)); check_refuse(label, f'B traced M={L + 1}', k, L)
        ev = open(glob.glob(f'{d}/trace-events-B_traced.txt')[0]).read()
        ok(f'{label} B traced: trace event names L', f'WHERE clause generated more than {L} rows. Switching to ORDER BY then post filter.' in ev)
        # B held
        mb = min(4 * L, N_T)
        c = cs.pop(0); w = window(trace, c); k = kinds(w)
        ok(f'{label} B held: 8 x rows i <= {mb}', c['ok'] and len(c['queries']) == Q and rows_ok(c, mb)); check_refuse(label, 'B held', k, L, Q)
        dd, db = held_delta(label, 'B_held', w, idle, idle_ms)
        ok(f'{label} B held: SkinnyPrimaryKey change = Q x (L + 1) = {Q * (L + 1)}', within(dd[SPK], Q * (L + 1)), f'{dd[SPK]:+d}')
        ok(f'{label} B held: BufferDecoratedKey change = Q x (L + 1)', within(dd[BDK], Q * (L + 1)), f'{dd[BDK]:+d}')
        bytes_check(label, 'B held', db, dd[SPK], b_unit)
        held[L] = dd[SPK]
        if L in (1000, 16000, 64000):
            c = cs.pop(0); k = kinds(window(trace, c))
            pr = k['proc']
            reads = fld(pr[0], 'reads') if len(pr) == 1 else None; proc = fld(pr[0], 'processed') if len(pr) == 1 else None
            ok(f'{label} C2 single: 10 rows, i <= {M_FAR}', rows_ok(c, M_FAR))
            if L < M_FAR:
                check_refuse(label, 'C2 single', k, L)
                ok(f'{label} C2 single: reads in [0.9 (N - M), N] = [{int(0.9 * (N_FAR - M_FAR))}, {N_FAR}]',
                   reads is not None and 0.9 * (N_FAR - M_FAR) <= reads <= N_FAR, f'reads={reads}')
                ok(f'{label} C2 single: processed = reads within 10', reads is not None and abs(proc - reads) <= 10, f'processed={proc}')
            else:
                check_allow(label, 'C2 single', k, M_FAR)
                ok(f'{label} C2 single: reads <= 20', reads is not None and reads <= 20, f'reads={reads}')
            c = cs.pop(0); w = window(trace, c); k = kinds(w)
            ok(f'{label} C2 held: 8 x rows', c['ok'] and len(c['queries']) == Q and rows_ok(c, M_FAR))
            dd, _ = held_delta(label, 'C2_held', w, idle, idle_ms)
            if L < M_FAR:
                ok(f'{label} C2 held: SkinnyPrimaryKey change >= 0.9 Q (N - M) = {int(0.9 * Q * (N_FAR - M_FAR))} and > Q M',
                   dd[SPK] >= 0.9 * Q * (N_FAR - M_FAR) and dd[SPK] > Q * M_FAR, f'{dd[SPK]:+d}')
            else:
                print(f'note {label} C2 held (list plan): SkinnyPrimaryKey change {dd[SPK]:+d} (recorded, no prediction)')
        ok(f'{label}: every client call consumed', not cs, f'left={len(cs)}')
    if all(x in held for x in (1000, 4000, 16000, 64000)):
        r = [held[x] / held[1000] for x in (1000, 4000, 16000, 64000)]
        print(f'note B held key ratio 1000:4000:16000:64000 = {" : ".join(f"{x:.3f}" for x in r)} (predicted 1 : 4.003 : 16.010 : 63.999)')


b = unit()
cluster(b)
print(f'TOTAL {len(res)} checks, {res.count(True)} ok, {res.count(False)} failed')
sys.exit(0 if all(res) else 1)
