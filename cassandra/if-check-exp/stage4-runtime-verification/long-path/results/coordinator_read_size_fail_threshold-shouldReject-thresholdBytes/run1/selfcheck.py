#!/usr/bin/env python3
"""Independent self-check of run 1, coordinator_read_size_fail_threshold (results §5). Re-parses the raw excerpts in this folder
(cluster/crs.trace, cluster/system-excerpt.log, cluster/summary.txt for the client outcomes, unit/harness.out) without using the
run script's computed EXPECTED lines, and recomputes every §9a relation from the source-derived constants.
usage: python3 selfcheck.py [folder]      prints one line per check and a total; exit 1 on any failure."""
import os, re, sys

D = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
S = 1008
ok_n = bad_n = 0


def chk(name, cond, detail=''):
    global ok_n, bad_n
    ok_n += bool(cond); bad_n += (not cond)
    print(f'{"ok  " if cond else "FAIL"} {name} {detail}')


nstar = lambda F: F // S + 1

# ---------------- cluster: trace, grouped into reads by a time gap > 500 ms
lines = []
for l in open(os.path.join(D, 'cluster/crs.trace')):
    m = re.search(r'ms=(\d+)', l)
    if m:
        lines.append((int(m.group(1)), l.strip()))
lines.sort(key=lambda x: x[0])
groups, cur, last = [], [], None
for t, l in lines:
    if last is not None and t - last > 500:
        groups.append(cur); cur = []
    cur.append(l); last = t
groups.append(cur)
chk('trace groups = 21 reads (instrument, warm-up, 3 control, 3x(A,B,B), 16M, C1x2, C2, C3, C5, C4)', len(groups) == 21, f'got {len(groups)}')


def kinds(g, k):
    return [l for l in g if l.startswith(k + ' ')]


def val(l, key):
    return int(re.search(rf'\b{key}=(-?\d+)', l).group(1))


def complete(g, rows, tag):
    r, f, c, gf = kinds(g, 'result'), kinds(g, 'frame'), kinds(g, 'coord-alloc'), kinds(g, 'guard-fail')
    good = (len(r) == 1 and val(r[0], 'rows') == rows and val(r[0], 'size') == S * rows and not gf and len(f) == 1
            and val(f[0], 'bytes') == 37 + 1020 * rows and len(c) == 1 and 'exit=normal' in c[0])
    chk(f'{tag}: completed, result size = 1008*{rows}, frame = 37 + 1020*{rows}, no guard-fail', good, str(r + f))
    return val(c[0], 'bytes') if c else None


def abort(g, F, tag):
    r, f, c, gf = kinds(g, 'result'), kinds(g, 'frame'), kinds(g, 'coord-alloc'), kinds(g, 'guard-fail')
    X = nstar(F) * S
    good = (len(gf) == 1 and 'ks=ks1' in gf[0] and val(gf[0], 'size') == X and val(gf[0], 'limit') == F and not r and not f
            and len(c) == 1 and 'exit=exception' in c[0])
    chk(f'{tag}: abort at F={F}, guard-fail size = X = {X}, no result, no frame, process() exited by exception', good, str(gf))
    return val(c[0], 'bytes') if c else None


ra = lambda g: [val(l, 'bytes') for l in kinds(g, 'read-alloc')]

complete(groups[0], 10, 'instrument ck<10')
abort(groups[1], 262144, 'warm-up (not a reading)')
ctl = {n: complete(groups[2 + i], n, f'control ck<{n}' if n < 8000 else 'control whole') for i, n in enumerate((1000, 2000, 8000))}
RA0 = ra(groups[4])[0]
a = (ctl[8000] - ctl[1000]) / 7000
print(f'info a = {a:.1f} B/row from coord-alloc of the controls; read-alloc(whole, unset) = {RA0}')
pair, whole_ab, ra_whole = {}, {}, {'unset': RA0}
gi = 5
for F in (262144, 1048576, 4194304):
    complete(groups[gi], nstar(F), f'A F={F} ck<n*'); gi += 1
    b1 = abort(groups[gi], F, f'B F={F} ck<n*+1'); gi += 1
    b2 = abort(groups[gi], F, f'B F={F} whole'); ra_whole[F] = ra(groups[gi])[0]; gi += 1
    pair[F] = (b1, b2); whole_ab[F] = b2
    chk(f'F={F}: coord-alloc whole abort within 5% of the n*+1 abort', abs(b2 - b1) / b1 <= 0.05, f'{b2} vs {b1} ({(b2 - b1) / b1:+.2%})')
complete(groups[gi], 8000, 'F=16777216 whole (above the data)'); ra_whole[16777216] = ra(groups[gi])[0]; gi += 1
ratio = (whole_ab[1048576] - whole_ab[262144]) / (whole_ab[4194304] - whole_ab[1048576])
chk('coord-alloc increments (1M-256K):(4M-1M) = 0.25 +/- 0.03', abs(ratio - 0.25) <= 0.03, f'{ratio:.4f}')
chk('abort at 262,144 allocates < 10% of the unset whole read', whole_ab[262144] < 0.10 * ctl[8000], f'{whole_ab[262144]} vs {ctl[8000]} ({whole_ab[262144] / ctl[8000]:.2%})')
slope = (whole_ab[4194304] - whole_ab[262144]) / (nstar(4194304) - nstar(262144))
print(f'info abort slope {slope:.1f} B/row vs completed-read a {a:.1f} (not a §9a cluster relation; recorded)')
chk('read-alloc(whole) within 5% of unset at every F', all(abs(v - RA0) / RA0 <= 0.05 for v in ra_whole.values()), str(ra_whole))
# C1 fetch 100
g = groups[gi]; gi += 1
res = kinds(g, 'result')
chk('C1 fetch 100: no guard-fail, results sum to 8,000 rows, each page <= 100 rows of 1008 B', not kinds(g, 'guard-fail')
    and sum(val(l, 'rows') for l in res) == 8000 and all(val(l, 'size') == S * val(l, 'rows') <= 100800 for l in res), f'{len(res)} pages')
abort(groups[gi], 262144, 'C1 fetch 1000 (page 1)'); gi += 1
g = groups[gi]; gi += 1
r = kinds(g, 'result')
chk('C2 count(*): one output row of 8 value bytes, no guard-fail', len(r) == 1 and val(r[0], 'rows') == 1 and val(r[0], 'size') == 8 and not kinds(g, 'guard-fail'), str(r))
complete(groups[gi], 8000, 'C3 switch off whole'); gi += 1
g = groups[gi]; gi += 1
gf = kinds(g, 'guard-fail')
chk('C5 scan: one guard-fail ks1 size 263,088 limit 262,144, no result, no frame', len(gf) == 1 and val(gf[0], 'size') == 263088 and val(gf[0], 'limit') == 262144
    and not kinds(g, 'result') and not kinds(g, 'frame'), str(gf))
g = groups[gi]; gi += 1
chk('C4: one guard-fail ks=system_schema limit=1, size > 1, no ks1 line', len(g) == 1 and 'ks=system_schema' in g[0] and val(g[0], 'limit') == 1 and val(g[0], 'size') > 1, str(g))

# ---------------- cluster: system.log
sl = open(os.path.join(D, 'cluster/system-excerpt.log')).read().splitlines()
warn = [l for l in sl if 'size failure threshold' in l]
want = ['262,144'] * 3 + ['1,048,576'] * 2 + ['4,194,304'] * 2 + ['262,144'] * 2
chk('system.log: 10 WARN lines (warm-up + 9 aborts), limits in order', len(warn) == 10
    and [re.search(r'threshold of ([\d,]+) bytes', l).group(1) for l in warn] == want + ['1'], str(len(warn)))
chk('system.log: WARN lines name ks1.t except the last (system_schema.keyspaces)', all('ks1.t' in l for l in warn[:9]) and 'system_schema.keyspaces' in warn[9])
upd = [re.search(r'to (\S+)$', l).group(1) for l in sl if 'updating  coordinator_read_size_fail_threshold' in l]
chk('system.log: the INFO updates in order', upd == ['262144B', 'null', '262144B', '1048576B', '4194304B', '16777216B', '262144B', '1B', '16777216B'], str(upd))

# ---------------- cluster: client outcomes (run-script READ lines)
reads = [l for l in open(os.path.join(D, 'cluster/summary.txt')) if l.startswith('READ ')]
errs = [l for l in reads if ': ERR ' in l]
chk('client: 9 reads failed, each ReadFailure with failure map {127.0.0.1: 4}', len(errs) == 9 and all("ERR ReadFailure codes={'127.0.0.1': 4}" in l for l in errs), str(len(errs)))
meter_ok = all(re.search(r'tmeter (\d+)->(\d+) cmeter (\d+)->(\d+)', l) and
               (lambda m: int(m[1]) - int(m[0]) == (1 if ('ERR' in l and 'system_schema' not in l) else 0) and int(m[3]) - int(m[2]) == (1 if 'ERR' in l else 0))(
                   re.search(r'tmeter (\d+)->(\d+) cmeter (\d+)->(\d+)', l).groups()) for l in reads)
chk('meters: table +1 per ks1 abort, client-request +1 per abort, 0 otherwise', meter_ok)
chk('WARN delta per aborted ks1 read is 1, per completed read 0', all(('warn+1' in l) == (': ERR ' in l) for l in reads))
c1 = [l for l in reads if 'C1 fetch 100' in l][0]
chk('C1 fetch 100 delivered 8000 rows', 'OK rows=8000' in c1, c1[:80])
c2 = [l for l in reads if 'C2 count' in l][0]
chk('C2 count(*) returned 8000', 'first=8000' in c2)

# ---------------- unit tier
u = open(os.path.join(D, 'unit/harness.out')).read().splitlines()
cl = [l for l in u if l.startswith('STAGE4 check')]
chk('unit: 101 checks, 0 MISMATCH', len(cl) == 101 and not any(l.endswith('MISMATCH') for l in cl), str(len(cl)))
info = {}
for l in u:
    m = re.match(r'STAGE4 info F=(\d+) (nplus1|whole|ck<n\*) aborted=(\w+) size=(\d+) pulled=(\d+) rows=(-?\d+)', l)
    if m:
        info[(int(m[1]), m[2])] = (m[3] == 'true', int(m[4]), int(m[5]), int(m[6]))
good = True
for F in (65536, 262144, 1048576):
    X = nstar(F) * S
    good &= info[(F, 'ck<n*')] == (False, X, nstar(F), nstar(F))
    good &= info[(F, 'nplus1')][:3] == (True, X, nstar(F) + 1) and info[(F, 'whole')][:3] == (True, X, nstar(F) + 1)
chk('unit: at 65,536 / 262,144 / 1,048,576 the n* read completes with X, both longer reads abort with X and n*+1 rows pulled', good)
ab = re.search(r'abort allocs \[(\d+), (\d+), (\d+)\] slope ([\d.]+) a ([\d.]+) ratio ([\d.]+)', '\n'.join(u))
d1, d2, d3 = int(ab[1]), int(ab[2]), int(ab[3]); ua = float(ab[5])
sl_ = (d3 - d1) / (1042 - 67); rt = (d2 - d1) / (d3 - d2)
chk('unit: abort slope within 15% of a (recomputed)', abs(sl_ - ua) / ua <= 0.15, f'{sl_:.1f} vs {ua:.1f}')
chk('unit: increment ratio 0.25 +/- 0.03 (recomputed)', abs(rt - 0.25) <= 0.03, f'{rt:.4f}')
fr = re.search(r'frame encodedSize ck<100 (\d+) ck<200 (\d+)', '\n'.join(u))
chk('unit: frame difference 102,000 B for 100 rows', int(fr[2]) - int(fr[1]) == 102000)

print(f'TOTAL ok {ok_n} fail {bad_n}')
sys.exit(1 if bad_n else 0)
