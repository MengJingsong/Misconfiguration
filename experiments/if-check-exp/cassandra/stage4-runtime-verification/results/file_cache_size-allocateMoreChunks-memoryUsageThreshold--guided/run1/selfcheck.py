#!/usr/bin/env python3
"""Independent self-check of run 1, file_cache_size-allocateMoreChunks-memoryUsageThreshold (results §5).
usage: selfcheck.py [<run1 log dir> [<unit log dir>]]     defaults: ~/stage4-logs/fcs/run1  ~/stage4-logs/fcs/unit
       (on the repository's excerpts: selfcheck.py run1/cluster run1/unit — bm.trace.excerpt keeps every made/dump/hold line,
        system.excerpt.log every limit/INFO/OOM/ERROR/WARN line, client.excerpt.log every client result line)
Re-parses the raw files only — samples.csv, phases.csv, bm.trace, nmt.csv, system.log, tablehistograms.txt, session.log and the
unit tier's harness.out / TEST-*.xml — without importing cluster-run.py, recomputes every figure the conclusion uses, checks the frozen
§9a relations (as amended 2026-10-14), and compares its own figures with the run script's result.json. Prints one line per check
("CHECK <id> ok|FAIL ...") and a final count. Exit 0 iff no check failed."""
import json, os, re, statistics, sys
from datetime import datetime, timezone

RUN = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/stage4-logs/fcs/run1')
UNIT = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser('~/stage4-logs/fcs/unit')
MIB = 1 << 20
M = 8 * MIB
VALUES = ['16', '64', '100', '128', 'default']
D_B = 200 * 20 * 64 * 1024
n_ok = n_fail = 0


def check(cid, cond, msg):
    global n_ok, n_fail
    if cond:
        n_ok += 1
    else:
        n_fail += 1
    print(f'CHECK {cid} {"ok" if cond else "FAIL"} {msg}')


def mib(x):
    return None if x is None else round(x / MIB, 2)


# ---------------- unit tier
uo = open(f'{UNIT}/harness.out').read().splitlines()
checks = [l for l in uo if l.startswith('STAGE4 check')]
check('U1', len(checks) == 96 and all(l.endswith(' OK') for l in checks), f'harness checks {len(checks)}, all OK: {all(l.endswith(" OK") for l in checks)}')
for mibv, ceil in ((16, 16), (20, 16), (64, 64), (100, 96)):
    fig = {l.split()[3]: dict(re.findall(r'(\w+)=(\d+)', l)) for l in uo if l.startswith(f'STAGE4 figures stage4-{mibv} ')}
    c, p, f5 = fig['1-ceiling'], fig['2-past'], fig['5-all-back']
    check(f'U2.{mibv}', int(c['pooled']) == ceil * MIB and int(c['overflow']) == 0, f'{mibv} MiB pool: pooled at ceiling {int(c["pooled"]) / MIB} MiB (expect {ceil}), overflow {c["overflow"]}')
    check(f'U3.{mibv}', int(p['overflow']) == 5 * 131072 and int(p['pooled']) == ceil * MIB and int(p['misses']) == 5,
          f'{mibv} MiB: five past the ceiling -> overflow {p["overflow"]} B, pooled unchanged, misses {p["misses"]}')
    check(f'U4.{mibv}', int(f5['pooled']) == ceil * MIB and int(f5['used']) == 0 and int(f5['overflow']) == 0,
          f'{mibv} MiB: all back -> pooled {int(f5["pooled"]) / MIB} MiB kept, used {f5["used"]}, overflow {f5["overflow"]}')
for x in ('TEST-org.apache.cassandra.utils.memory.BufferPoolTest.xml', 'TEST-org.apache.cassandra.utils.memory.BufferPoolCeilingTest.xml'):
    t = open(f'{UNIT}/{x}').read()
    m = re.search(r'<testsuite[^>]*errors="(\d+)"[^>]*failures="(\d+)"[^>]*tests="(\d+)"', t)
    check('U5', m and m.group(1) == '0' and m.group(2) == '0', f'{x}: tests {m.group(3) if m else "?"}, errors {m.group(1) if m else "?"}, failures {m.group(2) if m else "?"}')


# ---------------- cluster tier
def load(v):
    d = f'{RUN}/{v}'
    ph = dict((l.split(',')[0], int(l.split(',')[1])) for l in open(f'{d}/phases.csv').read().splitlines())
    rows = []
    for l in open(f'{d}/samples.csv').read().splitlines()[1:]:
        f = l.split(',')
        if len(f) == 13 and f[1] != 'ERR':
            rows.append(dict(zip('t0 t1 cap size used ofl pooled hits misses nsize nofl dused dcount'.split(), map(int, f))))
    errs = sum(1 for l in open(f'{d}/samples.csv').read().splitlines() if ',ERR,' in l)
    pick = lambda full, excerpt: f'{d}/{full}' if os.path.exists(f'{d}/{full}') else f'{d}/{excerpt}'
    tr = open(pick('bm.trace', 'bm.trace.excerpt')).read().splitlines()
    made = sorted(int(re.search(r'ms=(\d+)', l).group(1)) for l in tr if l.startswith('made '))
    dumps = [{k: int(x) for k, x in re.findall(r'(\w+)=(\d+)', l)} for l in tr if l.startswith('dump ')]
    holds = [{k: int(x) for k, x in re.findall(r'(\w+)=(\d+)', l)} for l in tr if l.startswith('hold ')]
    syslog = open(pick('system.log', 'system.excerpt.log'), errors='replace').read().splitlines()
    nmt = [l.split(',') for l in open(f'{d}/nmt.csv').read().splitlines()]
    hist = open(f'{d}/tablehistograms.txt').read()
    sess = open(pick('session.log', 'client.excerpt.log'), errors='replace').read()
    res = json.load(open(f'{d}/result.json'))
    return dict(ph=ph, rows=rows, errs=errs, made=made, dumps=dumps, holds=holds, syslog=syslog, nmt=nmt, hist=hist, sess=sess, res=res)


def logms(line):
    m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3})', line)
    return int(datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc).timestamp() * 1000) + int(m.group(2))


def dump_after(dumps, t):
    for x in dumps:
        if x['ms'] >= t:
            return x


SUM = {}
for v in VALUES:
    if not os.path.isdir(f'{RUN}/{v}'):
        check(f'C0.{v}', False, f'{v}: no log folder')
        continue
    L = load(v)
    ph, rows, made, r = L['ph'], L['rows'], L['made'], L['res']
    P = lambda t: sum(1 for m in made if m <= t) * M
    for x in rows:
        x['P'] = P(x['t0'])
    win = lambda a, b: [x for x in rows if ph[a] <= x['t0'] <= ph[b]]
    idle, A, B = win('idle', 'A'), win('A', 'A_end'), win('B', 'B_end')
    post = [x for x in rows if ph['after'] - 5000 <= x['t0'] <= ph['after'] + 5000]
    # resolved limit
    st = [l for l in L['syslog'] if 'Global buffer pool limit is' in l]
    lim = float(re.search(r'limit is ([\d.]+)MiB for chunk-cache', st[-1]).group(1)) if st else None
    T = int(lim * MIB) if lim else None
    cap = {x['cap'] for x in rows}
    want = 512 * MIB if v == 'default' else int(v) * MIB
    check(f'C1.{v}', T == want and cap == {want}, f'{v}: startup line {lim} MiB, Capacity gauge {sorted(cap)} (expect {want})')
    ceiling = (want // M) * M
    sat = v != 'default'
    check(f'C2.{v}', L['errs'] == 0 and len(rows) >= 250, f'{v}: sampler rows {len(rows)}, error rows {L["errs"]}')
    # A
    dA0, dA1, dB0, dB1 = (dump_after(L['dumps'], ph[k]) for k in ('A', 'A_end', 'B', 'B_end'))
    a_pmax = max(x['P'] for x in A)
    check(f'C3.{v}', a_pmax <= 16 * MIB and max(x['ofl'] for x in A) == 0 and dA1['overflow'] - dA0['overflow'] == 0,
          f'{v}: A P max {mib(a_pmax)} MiB (<= 16), O max {max(x["ofl"] for x in A)}, overflow allocations {dA1["overflow"] - dA0["overflow"]}')
    # B
    first_o = next((x['t0'] for x in B if x['ofl'] > 0), None)
    o_peak = max(x['ofl'] for x in B)
    b_pmax = max(x['P'] for x in B)
    refuse = dB1['refuse'] - dB0['refuse']
    ofl_n = dB1['overflow'] - dB0['overflow']
    ofl_b = dB1['overflow_bytes'] - dB0['overflow_bytes']
    info = [l for l in L['syslog'] if 'Maximum memory usage reached' in l]
    oom = [l for l in L['syslog'] if 'failed to allocate chunk' in l]
    misses = B[-1]['misses'] - B[0]['misses']
    idle_d = statistics.median(x['dused'] for x in idle)
    d_rise = max(x['dused'] for x in B) - idle_d
    inhold = max((h['inhold'] for h in L['holds'] if ph['B'] <= h['ms'] <= ph['B_end']), default=0)
    hv = {f[0]: float(f[3]) for f in (l.split() for l in L['hist'].splitlines()) if len(f) >= 4 and f[0] in ('50%', '99%')}
    check(f'C4.{v}', hv.get('50%') == 20 and hv.get('99%') == 20 and inhold >= 180, f'{v}: SSTables per read {hv}, max reads in the hold {inhold}')
    check(f'C5.{v}', len(made) * M <= want, f'{v}: macro chunks made in the lifetime {len(made)} = {mib(len(made) * M)} MiB <= T')
    check(f'C6.{v}', not oom, f'{v}: OOM fallback lines {len(oom)}')
    if sat:
        after = [x for x in B if first_o and x['t0'] >= first_o]
        check(f'C7.{v}', after and all(x['P'] == ceiling for x in after), f'{v}: P after the first O > 0: {sorted({mib(x["P"]) for x in after})} MiB (expect {mib(ceiling)})')
        check(f'C8.{v}', first_o and (ph['B_end'] - first_o) >= 120000, f'{v}: first O > 0 at +{(first_o - ph["B"]) / 1000:.1f} s; {(ph["B_end"] - first_o) / 1000:.1f} s sampled after it')
        check(f'C9.{v}', 0.9 * D_B <= ceiling + o_peak <= D_B + 16 * MIB, f'{v}: P + O_peak = {mib(ceiling)} + {mib(o_peak)} = {mib(ceiling + o_peak)} MiB in [225, 266]')
        check(f'C10.{v}', refuse > 0 and ofl_n > 0 and misses > 0 and ofl_b == ofl_n * 65536,
              f'{v}: refusals {refuse}, overflow allocations {ofl_n} of {ofl_b} B (= n x 65,536: {ofl_b == ofl_n * 65536}), Misses +{misses}')
        inB = [l for l in info if ph['A'] <= logms(l) <= ph['B_end'] + 1000]
        check(f'C11.{v}', len(info) == 1 and 'for chunk-cache buffer pool, cannot allocate chunk of 8.000MiB' in info[0],
              f'{v}: INFO lines {len(info)} (in A..B: {len(inB)}): {info[0][:160] if info else ""}')
        check(f'C12.{v}', ceiling + o_peak - 8 * MIB <= d_rise <= ceiling + o_peak + 40 * MIB,
              f'{v}: direct MemoryUsed rise {mib(d_rise)} MiB in [{mib(ceiling + o_peak - 8 * MIB)}, {mib(ceiling + o_peak + 40 * MIB)}]')
    else:
        check(f'C7.{v}', 248 * MIB <= b_pmax <= 264 * MIB, f'{v}: B P max {mib(b_pmax)} MiB in [248, 264]')
        check(f'C8.{v}', o_peak == 0 and ofl_n == 0 and refuse == 0 and misses == 0, f'{v}: O peak {o_peak}, overflow allocations {ofl_n}, refusals {refuse}, Misses +{misses}')
        check(f'C11.{v}', len(info) == 0, f'{v}: INFO lines {len(info)}')
        check(f'C12.{v}', b_pmax - 8 * MIB <= d_rise <= b_pmax + 40 * MIB, f'{v}: direct MemoryUsed rise {mib(d_rise)} MiB in [{mib(b_pmax - 8 * MIB)}, {mib(b_pmax + 40 * MIB)}]')
    check(f'C13.{v}', post and all(x['ofl'] == 0 for x in post) and all(x['P'] == b_pmax for x in post) and all(x['pooled'] == b_pmax for x in post),
          f'{v}: after B: O {sorted({x["ofl"] for x in post})}, P (trace) {sorted({mib(x["P"]) for x in post})}, Size-OverflowSize {sorted({mib(x["pooled"]) for x in post})} MiB')
    # client
    cl = re.findall(r'(?:OK|ERR) (\{"ok".*?\})\n', L['sess'])
    reads = [json.loads(c) for c in cl if '"concurrency"' in c]
    check(f'C14.{v}', len(reads) == 2 and all(x['ok'] and x['wrong_row_count'] == 0 for x in reads),
          f'{v}: client A {reads[0]["reads"] if reads else "?"} reads, B {reads[1]["reads"] if len(reads) > 1 else "?"} reads, all ok with 4 rows')
    # NMT
    nm = {f[0]: f for f in L['nmt']}
    nmt_idle = int(nm['idle'][2])
    nmt_bmax = max(int(f[2]) for k, f in nm.items() if k.startswith('B_'))
    nmt_rise = (nmt_bmax - nmt_idle) / 1024
    # agreement with the run script
    agree = (r['B_overflow_max'] == o_peak and r['B_pbm_max'] == b_pmax and r['B_direct_rise'] == d_rise and r['A_pbm_max'] == a_pmax
             and r.get('B_bm_refuse') == refuse and r.get('B_bm_overflow') == ofl_n and abs((r['nmt_B_other_rise_mib'] or 0) - round(nmt_rise, 1)) < 0.11)
    check(f'C15.{v}', agree, f'{v}: own figures equal result.json (O peak, P, direct rise, refusals, overflow, NMT)')
    SUM[v] = dict(T=want, ceiling=ceiling, P_idle=max(x['P'] for x in idle), P_A=a_pmax, P_B=b_pmax, O_peak=o_peak, size_peak=max(x['size'] for x in B),
                  d_rise=d_rise, nmt_rise=nmt_rise, refuse=refuse, ofl_n=ofl_n, ofl_b=ofl_b, misses=misses, hits=B[-1]['hits'] - B[0]['hits'],
                  info=len(info), first_o=None if first_o is None else round((first_o - ph['B']) / 1000, 1), inhold=inhold,
                  reads_B=reads[1]['reads'] if len(reads) > 1 else None, made=len(made), idle_direct=idle_d, nmt_idle=nmt_idle / 1024)

# ---------------- across values
if all(v in SUM for v in VALUES):
    s = SUM
    check('X1', [mib(s[v]['P_B']) for v in ('16', '64', '100', '128')] == [16, 64, 96, 128],
          f'plateau P_B 16/64/100/128: {[mib(s[v]["P_B"]) for v in ("16", "64", "100", "128")]} MiB (expect 16, 64, 96, 128)')
    tot = [s[v]['ceiling'] + s[v]['O_peak'] for v in ('16', '64', '100', '128')]
    check('X2', max(tot) - min(tot) <= 28 * MIB, f'P + O_peak at the saturated values {[mib(t) for t in tot]} MiB, spread {mib(max(tot) - min(tot))} <= 28')
    dr = [s[v]['d_rise'] for v in VALUES]
    check('X3', max(dr) - min(dr) <= 28 * MIB, f'direct rise over idle, all five values {[mib(x) for x in dr]} MiB, spread {mib(max(dr) - min(dr))} <= 28')
    nr = [s[v]['nmt_rise'] for v in VALUES]
    check('X4', max(nr) - min(nr) <= 28, f'NMT Other rise over idle, all five values {[round(x, 1) for x in nr]} MiB, spread {max(nr) - min(nr):.1f} <= 28 (frozen 9a clause)')
    check('X5', all(s[v]['nmt_rise'] <= mib(s[v]['ceiling' if v != 'default' else 'P_B'] + s[v]['O_peak']) + 40 for v in VALUES),
          'NMT Other rise within P + O_peak + 40 MiB at every value (frozen 9a clause): '
          + str([(v, round(s[v]['nmt_rise'], 1)) for v in VALUES]))
    print('TABLE value | T MiB | ceiling | P idle | P A | P B | O peak | P+O | Size peak | direct rise | NMT Other rise | refusals | overflow n | Misses | INFO | first O s | in hold | B reads')
    for v in VALUES:
        x = s[v]
        print(f'TABLE {v} | {mib(x["T"])} | {mib(x["ceiling"])} | {mib(x["P_idle"])} | {mib(x["P_A"])} | {mib(x["P_B"])} | {mib(x["O_peak"])} | '
              f'{mib((x["ceiling"] if v != "default" else x["P_B"]) + x["O_peak"])} | {mib(x["size_peak"])} | {mib(x["d_rise"])} | {round(x["nmt_rise"], 1)} | '
              f'{x["refuse"]} | {x["ofl_n"]} | {x["misses"]} | {x["info"]} | {x["first_o"]} | {x["inhold"]} | {x["reads_B"]}')
print(f'SELFCHECK {n_ok} ok, {n_fail} failed')
sys.exit(0 if n_fail == 0 else 1)
