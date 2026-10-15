#!/usr/bin/env python3
"""Independent self-check of run 1, max_hints_size_per_host-shouldHint-maxHintsSize (results §5).
Re-parses the raw files with its own code (it imports nothing from the harness) and re-judges §9a's frozen relations:
  <logs>/mhs.trace       N1's Byteman trace (decide / site send / flush / roll lines)
  <logs>/du.csv          the 1 s sampler: ms, label, host id, bytes of the host's .hints files on N1, file count
  <logs>/phases.csv      phase name, epoch ms
  <logs>/counters.csv    tag, ms, metric, value (JMX on N1)
  <logs>/keys/<tag>.csv  the writer's per-row log: pk, ms sent, ok|err
  <logs>/readback/N2-keys.txt, N3-keys.txt   every pk read on that host alone
  <logs>/hostids.json
  <unit>/summary.txt, <unit>/harness.out, <unit>/TEST-*.xml
usage: selfcheck.py [<logs> [<unit>]]   (defaults ~/stage4-logs/mhs/run1 and ~/stage4-logs/mhs/unit)
Prints one line per check, "ok" or "FAIL", and a summary; exit 0 if every check holds."""
import csv, glob, json, os, re, sys
from collections import defaultdict

LOGS = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/mhs/run1')
UNIT = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser('~/stage4-logs/mhs/unit')
MIB = 1 << 20
EP = {'N1': '/127.0.0.2:7010', 'N2': '/127.0.0.3:7010', 'N3': '/127.0.0.4:7010'}
res = {'ok': 0, 'fail': 0}
fails = []


def chk(name, cond, detail=''):
    res['ok' if cond else 'fail'] += 1
    if not cond:
        fails.append(name)
    print(f'{"ok  " if cond else "FAIL"} {name}' + (f' — {detail}' if detail else ''))


# ------------------------------------------------------------------ parse
hostid = json.load(open(f'{LOGS}/hostids.json'))
H2, H3 = hostid['N2'], hostid['N3']

phases = {}
for name, ms in csv.reader(open(f'{LOGS}/phases.csv')):
    phases[name] = int(ms)          # a later lifetime in the same folder would overwrite; run 1 has one

dec, site, flush, roll, other = [], [], [], [], 0
rx_d = re.compile(r'^decide ep=(\S+) result=(true|false) checked=(-?\d+) limit=(-?\d+) ms=(\d+)$')
rx_s = re.compile(r'^site send ep=(\S+) result=(true|false) key=([0-9a-f]+) ms=(\d+)$')
rx_f = re.compile(r'^flush host=(\S+) size=(\d+) ms=(\d+)$')
rx_r = re.compile(r'^roll host=(\S+) ms=(\d+)$')
for line in open(f'{LOGS}/mhs.trace'):
    line = line.rstrip('\n')
    m = rx_d.match(line)
    if m:
        dec.append(dict(ms=int(m[5]), ep=m[1], ok=m[2] == 'true', T=int(m[3]), L=int(m[4])))
        continue
    m = rx_s.match(line)
    if m:
        site.append(dict(ms=int(m[4]), ep=m[1], ok=m[2] == 'true', key=int(m[3], 16)))
        continue
    m = rx_f.match(line)
    if m:
        flush.append(dict(ms=int(m[3]), host=m[1], size=int(m[2])))
        continue
    m = rx_r.match(line)
    if m:
        roll.append(dict(ms=int(m[2]), host=m[1]))
        continue
    if line.strip():
        other += 1

du = defaultdict(list)          # host id -> [(ms, bytes, files)]
own = []
for row in csv.reader(open(f'{LOGS}/du.csv')):
    ms, lab, h, b, n = row
    if lab.endswith('-own-dir'):
        own.append((int(ms), lab, int(b)))
    else:
        du[h].append((int(ms), int(b), int(n)))
for h in du:
    du[h].sort()

cnt = defaultdict(dict)          # tag -> metric -> value
for tag, ms, k, v in csv.reader(open(f'{LOGS}/counters.csv')):
    cnt[tag][k] = int(v)

keys = {}
for f in sorted(glob.glob(f'{LOGS}/keys/*.csv')):
    tag = os.path.basename(f)[:-4]
    keys[tag] = [(int(a), int(b), c) for a, b, c in csv.reader(open(f))]


def du_at(h, ms):
    best = (0, 0)
    for t, b, n in du[h]:
        if t <= ms:
            best = (b, n)
        else:
            break
    return best


def created(tag, node):
    return cnt[tag].get('Hints_created-' + EP[node].replace(':', '.'), 0)


def rows_per_s(tag):
    k = keys[tag]
    return (len(k) - 1) / ((k[-1][1] - k[0][1]) / 1000.0)


print(f'parsed: {len(dec)} decide, {len(site)} site send, {len(flush)} flush, {len(roll)} roll, {other} other trace lines; '
      f'{sum(len(v) for v in du.values())} du samples; phases {len(phases)}; key logs {sorted(keys)}')
chk('trace has no unparsed lines', other == 0, f'{other}')

# ------------------------------------------------------------------ unit tier
print('--- unit tier')
us = open(f'{UNIT}/summary.txt').read()
m = re.search(r'StorageProxyTest exit=(\d+) Tests run: (\d+), Failures: (\d+), Errors: (\d+)', us)
chk('upstream StorageProxyTest passes', bool(m) and m[1] == '0' and m[3] == '0' and m[4] == '0', m and m[0])
x = open(glob.glob(f'{UNIT}/TEST-org.apache.cassandra.service.StorageProxyTest*.xml')[0]).read()
tc = re.search(r'<testcase [^>]*name="testShouldHintOnExceedingSize[^"]*"[^>]*?(/?)>', x)
chk('upstream testShouldHintOnExceedingSize ran without failure (self-closing testcase, no failure/error element in the file)',
    bool(tc) and tc[1] == '/' and not re.search(r'<(failure|error)', x), tc and tc[0])
ho = open(f'{UNIT}/harness.out').read()
lines = re.findall(r'^STAGE4 check (.*) expected=(\S+) actual=(\S+) (ok|MISMATCH)$', ho, re.M)
chk('harness: every STAGE4 check line re-judged equal', all(e == a for _, e, a, _ in lines) and len(lines) > 0, f'{len(lines)} checks')
chk('harness: no line marked MISMATCH', not any(s == 'MISMATCH' for *_, s in lines))
need = {'3 T exactly 1 MiB': ('1048576', '1048576'), '3 shouldHint T == L = 1048576': ('true', 'true'),
        '3 shouldHint T == L + 1': ('false', 'false'), '2 limit bytes': ('1048576', '1048576'),
        '6 shouldHint true while T0 + buffered > L': ('true', 'true'), '6 shouldHint after flush': ('false', 'false')}
got = {n: (e, a) for n, e, a, _ in lines}
for n, v in need.items():
    chk(f'harness: step "{n}"', got.get(n) == v, str(got.get(n)))
mx = re.search(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+)', us.split('ShouldHintSizeTest')[1]) if 'ShouldHintSizeTest' in us else None
chk('harness test: 3 tests, 0 failures, 0 errors', bool(mx) and mx.groups() == ('3', '0', '0'), mx and mx[0])

# ------------------------------------------------------------------ whole-run invariants
print('--- whole run')
over = [d for d in dec if d['ok'] and d['L'] > 0 and d['T'] > d['L']]
chk('no decide true with checked > limit > 0 anywhere (no bypass)', not over, f'{len(over)}')
other_false = [d for d in dec if not d['ok'] and not (d['L'] > 0 and d['T'] > d['L'])]
chk('every decide false anywhere has checked > limit > 0 (no other rejection)', not other_false, f'{len(other_false)}')
chk('no decide for N1 itself', not [d for d in dec if d['ep'] == EP['N1']])
ns = {t: sum(v for k, v in c.items() if k.startswith('Hints_not_stored-')) for t, c in cnt.items()}
chk('Hints_not_stored absent or 0 at every counter read', all(v == 0 for v in ns.values()), str(ns))
chk('N2 and N3 own hints directories empty in every sample', all(b == 0 for _, _, b in own), f'{len(own)} samples')
for tag, k in keys.items():
    chk(f'writer {tag}: every row ok', all(c == 'ok' for *_, c in k), f'{sum(c != "ok" for *_, c in k)} of {len(k)} not ok')
allpk = [pk for k in keys.values() for pk, _, _ in k]
chk('writer: keys distinct across the lifetime', len(allpk) == len(set(allpk)), f'{len(allpk)}')

# ------------------------------------------------------------------ control
print('--- control')
c0, c1 = phases['control stream start'], phases['control stream end']
chk('control: no decide line', not [d for d in dec if c0 <= d['ms'] <= c1 + 3000])
chk('control: no site send line', not [s for s in site if c0 <= s['ms'] <= c1 + 3000])
chk('control: no flush line', not [f for f in flush if c0 <= f['ms'] <= c1 + 3000])
chk('control: Hints_created 0', sum(v for k, v in cnt['control after'].items() if k.startswith('Hints_created-')) == 0)

# ------------------------------------------------------------------ enabled arms
arms = [t[:-len(' stream start')] for t in phases if t.endswith(' stream start') and re.match(r'^(L|two)\d+ ', t)]
print('--- enabled arms', arms)
rows = []
for arm in arms:
    mib = int(re.sub(r'\D', '', arm))
    L = mib * MIB
    node = 'N2' if arm.startswith('two') else 'N3'
    h = hostid[node]
    t0, t1 = phases[f'{arm} stream start'], phases[f'{arm} stream end']
    cb, ca = f'{arm} before', f'{arm} after'
    ds = [d for d in dec if d['ep'] == EP[node] and t0 <= d['ms'] <= t1 + 3000]
    ff = next((d for d in ds if not d['ok']), None)
    chk(f'{arm}: a refusal exists for {node}', ff is not None)
    if ff is None:
        continue
    chk(f'{arm}: first refusal equals the run script\'s', ff['ms'] == phases.get(f'{arm} first false'), f'{ff["ms"]} vs {phases.get(arm + " first false")}')
    a_part = [d for d in ds if d['ms'] < ff['ms']]
    b_part = [d for d in ds if d['ms'] >= ff['ms']]
    chk(f'{arm}: every decide limit = {L}', {d['L'] for d in ds} == {L})
    chk(f'{arm}: A all true with checked <= L ({len(a_part)})', all(d['ok'] and 0 <= d['T'] <= L for d in a_part))
    chk(f'{arm}: B all false with checked > L ({len(b_part)})', all((not d['ok']) and d['T'] > L for d in b_part))
    T0 = du_at(h, t0)[0]
    after_ms = max(t for t, _, _ in du[h] if t <= t1 + 3500)
    T_end, files_end = du_at(h, t1 + 3500)
    fl = [f for f in flush if f['host'] == h and f['ms'] <= ff['ms']]
    cross, prev = fl[-1], fl[-2]
    chk(f'{arm}: the crossing flush size equals the first refusal\'s operand', cross['size'] == ff['T'] or files_end > 1,
        f'{cross["size"]} vs {ff["T"]} (files {files_end})')
    chk(f'{arm}: the flush before it left the operand <= L', prev['size'] <= L or files_end > 1, f'{prev["size"]}')
    Fp = cross['ms'] - prev['ms']
    st = [s for s in site if s['ep'] == EP[node] and t0 <= s['ms'] <= t1 + 3000]
    st_true = sum(s['ok'] for s in st)
    H = (T_end - T0) / st_true
    rps = rows_per_s(arm)
    r = H * rps
    bound = L + r * Fp / 1000 + H
    g60 = T_end - du_at(h, max(ff['ms'] + 5000, t1 - 60000))[0]
    cd = created(ca, node) - created(cb, node)
    td = cnt[ca].get('TotalHints', 0) - cnt[cb].get('TotalHints', 0)
    true_all = sum(1 for s in site if t0 <= s['ms'] <= t1 + 3000 and s['ok'])
    wr = len(keys[arm])
    chk(f'{arm}: T_end in (L, L + r*F\'+H], F\' literal (frozen Prediction)', L < T_end <= bound,
        f'T_end {T_end}, L {L}, bound {bound:.0f} (r {r:.0f}, F\' {Fp} ms, H {H:.1f}), over by {T_end - bound:.0f} B')
    # flush lines of one flush task: a 128 MiB roll inside a task gives two session lines a few ms apart
    allf = [f for f in flush if f['host'] == h]
    tasks = []
    for f in allf:
        if tasks and f['ms'] - tasks[-1][-1]['ms'] < 100:
            tasks[-1].append(f)
        else:
            tasks.append([f])
    ci = max(i for i, tk in enumerate(tasks) if tk[0]['ms'] <= ff['ms'])
    Ft = tasks[ci][-1]['ms'] - tasks[ci - 1][-1]['ms']
    bt = L + r * Ft / 1000 + H
    chk(f'{arm}: T_end in (L, L + r*F\'+H], F\' between flush tasks (interpretation)', L < T_end <= bt,
        f'F\' task {Ft} ms ({len(tasks[ci])} session line(s) in the crossing task), bound {bt:.0f}, over by {T_end - bt:.0f} B')
    bF = L + r * 1.0 + H
    chk(f'{arm}: T_end in (L, L + r*F+H], F = 1 s (Conclusions row 1)', L < T_end <= bF, f'bound {bF:.0f}, margin {bF - T_end:.0f} B')
    chk(f'{arm}: T_end <= L + 2 MiB', T_end <= L + 2 * MIB, f'overshoot {T_end - L} B = {(T_end - L) / MIB:.3f} MiB')
    chk(f'{arm}: 0 bytes over B\'s last 60 s', g60 == 0, f'{g60}')
    chk(f'{arm}: no site send true after the first refusal', not [s for s in st if s['ok'] and s['ms'] > ff['ms']])
    chk(f'{arm}: one site send line per row written', len(st) == wr, f'{len(st)} vs {wr}')
    chk(f'{arm}: Hints_created {node} delta = site send true', cd == st_true, f'{cd} vs {st_true}')
    chk(f'{arm}: TotalHints delta = site send true (all hosts)', td == true_all, f'{td} vs {true_all}')
    # sub-prediction (frozen): files minus the operand the check last read, within one flush's bytes
    gap = 0
    j = 0
    srt = sorted(d for d in [(d['ms'], d['T']) for d in a_part])
    for t, b, n in du[h]:
        if t < t0 or t > ff['ms']:
            continue
        while j + 1 < len(srt) and srt[j + 1][0] <= t:
            j += 1
        if srt and srt[j][0] <= t:
            gap = max(gap, b - srt[j][1])
    chk(f'{arm}: (sub) files - last checked operand in A <= r*F\'+H', gap <= r * Fp / 1000 + H, f'max {gap} vs {r * Fp / 1000 + H:.0f}')
    rows.append((arm, node, L, T0, T_end, T_end - L, Fp, round(H, 1), round(rps, 2), round(bound), len(a_part), len(b_part), cd))

print('arm,host,L,T0,T_end,overshoot,Fprime_ms,H,rows_per_s,bound,A_decides,B_decides,created')
for r_ in rows:
    print(','.join(str(x) for x in r_))
Ls = [r_ for r_ in rows if r_[0].startswith('L')]
chk('plateau follows L: T_end - L in (0, 2 MiB] at every enabled value', all(0 < r_[5] <= 2 * MIB for r_ in Ls), str([r_[5] for r_ in Ls]))
chk('plateau ordering follows L', [r_[4] for r_ in Ls] == sorted(r_[4] for r_ in Ls) and len({r_[2] for r_ in Ls}) == len(Ls))

two = [a for a in arms if a.startswith('two')]
if two:
    a = two[0]
    t0, t1 = phases[f'{a} stream start'], phases[f'{a} stream end']
    d3 = [d for d in dec if d['ep'] == EP['N3'] and t0 <= d['ms'] <= t1 + 3000]
    chk(f'{a}: every N3 decide false with checked > limit', d3 and all((not d['ok']) and d['T'] > d['L'] > 0 for d in d3), f'{len(d3)}')
    b3a, b3b = du_at(H3, t0 - 1)[0], du_at(H3, t1 + 3500)[0]
    chk(f'{a}: N3 files unchanged over the arm', b3a == b3b, f'{b3a} -> {b3b}')
    chk(f'{a}: no N3 flush line during the arm', not [f for f in flush if f['host'] == H3 and t0 <= f['ms'] <= t1 + 3000])
    chk(f'{a}: Hints_created N3 delta 0', created(f'{a} after', 'N3') == created(f'{a} before', 'N3'))
    print(f'{a}: directory total N3 {b3b} + N2 {du_at(H2, t1 + 3500)[0]} = {b3b + du_at(H2, t1 + 3500)[0]}')

# ------------------------------------------------------------------ default arm
print('--- default arm')
t0, t1 = phases['default stream start'], phases['default stream end']
Hm = sum(r_[7] for r_ in Ls) / len(Ls)
pred = Hm * rows_per_s('default') * (t1 - t0) / 1000
g = {}
for node, h in (('N2', H2), ('N3', H3)):
    dd = [d for d in dec if d['ep'] == EP[node] and t0 <= d['ms'] <= t1 + 3000]
    chk(f'default: every {node} decide true, limit 0, checked -1', dd and all(d['ok'] and d['L'] == 0 and d['T'] == -1 for d in dd), f'{len(dd)}')
    b0, n0 = du_at(h, t0 - 1)
    b1, n1 = du_at(h, t1 + 3500)
    g[node] = b1 - b0
    l60 = b1 - du_at(h, max(t0 + 5000, t1 - 60000))[0]
    rl = [x for x in roll if x['host'] == h and t0 <= x['ms'] <= t1 + 3000]
    chk(f'default: {node} growth 0.8-1.2 x predicted', 0.8 <= g[node] / pred <= 1.2, f'{g[node]} vs {pred:.0f} ({g[node] / pred:.3f})')
    chk(f'default: {node} growing in the last 60 s', l60 > 0, f'{l60}')
    chk(f'default: {node} passed a 128 MiB roll', len(rl) >= 1 and n1 > n0, f'rolls {len(rl)}, files {n0} -> {n1}')
    st_true = sum(1 for s in site if s['ep'] == EP[node] and t0 <= s['ms'] <= t1 + 3000 and s['ok'])
    chk(f'default: Hints_created {node} delta = site send true', created('default after', node) - created('default before', node) == st_true)
    # at the default, no plateau: the files pass every enabled value's plateau
    chk(f'default: {node} files end above every enabled limit + 2 MiB', b1 > max(r_[2] for r_ in Ls) + 2 * MIB, f'{b1}')
chk('default: the two hosts grow alike (within 5 %)', abs(g['N2'] / g['N3'] - 1) <= 0.05, f'{g["N2"] / g["N3"]:.4f}')

# ------------------------------------------------------------------ read-back
print('--- read-back')
written = {pk: tag for tag, k in keys.items() for pk, _, c in k if c == 'ok'}
up2 = {'control'} | {a for a in arms if a.startswith('L')}
sets = {n: {True: set(), False: set()} for n in ('N2', 'N3')}
for s in site:
    for n in ('N2', 'N3'):
        if s['ep'] == EP[n]:
            sets[n][s['ok']].add(s['key'])
exp = {'N3': {k for k, t in written.items() if t == 'control'} | sets['N3'][True],
       'N2': {k for k, t in written.items() if t in up2} | sets['N2'][True]}
chk('read-back: every site send key is a written key', all(k in written for n in sets for v in sets[n].values() for k in v))
chk('read-back: no key both true and false for one host', all(not (sets[n][True] & sets[n][False]) for n in sets))
for n in ('N3', 'N2'):
    got_ = {int(x) for x in open(f'{LOGS}/readback/{n}-keys.txt') if x.strip()}
    miss = set(written) - got_
    chk(f'read-back {n}: rows held = expected exactly', got_ == exp[n], f'held {len(got_)}, expected {len(exp[n])}, extra {len(got_ - exp[n])}, short {len(exp[n] - got_)}')
    chk(f'read-back {n}: missing rows = its refused rows', miss == sets[n][False], f'missing {len(miss)}, refused {len(sets[n][False])}')
    print(f'read-back {n}: written {len(written)}, held {len(got_)}, missing {len(miss)} ({100 * len(miss) / len(written):.1f} %)')

print(f'SUMMARY ok {res["ok"]} fail {res["fail"]}' + (f' — failed: {fails}' if fails else ''))
sys.exit(0 if res['fail'] == 0 else 1)
