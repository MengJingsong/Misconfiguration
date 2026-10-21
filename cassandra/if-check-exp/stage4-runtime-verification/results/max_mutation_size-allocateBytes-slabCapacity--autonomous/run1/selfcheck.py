#!/usr/bin/env python3
"""Independent self-check of run 1, max_mutation_size-allocateBytes-slabCapacity--autonomous (results §5).
usage: selfcheck.py <run1 log root>     (pc06: ~/stage4-logs/mss/run1)
Re-parses the raw files only: unit/harness.out and unit/TEST-*.xml; per lifetime cluster/<arm>-<rep>/samples.csv,
mss.trace, and the client JSON lines quoted in summary.txt ("S result:", "L write", "X write"). It does not read
phases.json or analysis.json for any value; it uses its own baseline (the last sample before the bulk client's own
ms_start) and its own end (the last sample), then compares its figures with the run script's printed ones.
Prints one "CHECK <name> ok|FAIL <detail>" line per relation and a table of the recomputed readings."""
import ast, csv, json, os, re, statistics, sys, time
from xml.etree import ElementTree

R = sys.argv[1]
MIB = 1 << 20
BAND = 8 * MIB
res = {'ok': 0, 'fail': 0}
SLAB = {'D': 32 * MIB, 'M4': 32 * MIB, 'M32': 64 * MIB, 'B1': 32 * MIB}
KMAX = {'D': 3, 'M4': 3, 'M32': 3, 'B1': 1}


def check(name, cond, detail=''):
    res['ok' if cond else 'fail'] += 1
    print(f'CHECK {name} {"ok" if cond else "FAIL"} {detail}')
    return cond


# ------------------------------------------------------------------ unit
U = R + '/unit'
lines = open(U + '/harness.out').read().splitlines()
chk = [l for l in lines if l.startswith('STAGE4 check ')]
mm = [l for l in chk if ' MISMATCH ' in l]
check('unit: harness checks all ok', len(chk) > 0 and not mm, f'{len(chk)} checks, {len(mm)} mismatches')
ncase = 0
for l in lines:
    m = re.match(r'STAGE4 case C=(\d+)MiB h=(\d+) n=(\d+) expected_n=(\d+) sum=(\d+) C=(\d+) remaining_after=(\d+) closed=(\w+)', l)
    if m:
        ncase += 1
        c, h, n, s, rem, cl = int(m.group(1)) * MIB, int(m.group(2)), int(m.group(3)), int(m.group(5)), int(m.group(7)), m.group(8)
        mine = c // (h + 12)
        check(f'unit: C={c // MIB}MiB h={h}: n = floor(C/(h+12)) recomputed', n == mine and s == n * (h + 12) <= c
              and s + h + 12 > c and rem == 0 and cl == 'true', f'n={n} mine={mine} sum={s} C={c} next={s + h + 12}')
    m = re.match(r'STAGE4 case C=(\d+)MiB create direct_used (\d+)->(\d+) count (\d+)->(\d+)', l)
    if m:
        c = int(m.group(1)) * MIB
        check(f'unit: C={c // MIB}MiB create: direct +C, Count +1', int(m.group(3)) - int(m.group(2)) == c
              and int(m.group(5)) - int(m.group(4)) == 1, l[12:])
check('unit: 9 fill cases parsed', ncase == 9, f'{ncase}')
for f in sorted(os.listdir(U)):
    if f.startswith('TEST-') and f.endswith('.xml'):
        t = ElementTree.parse(U + '/' + f).getroot()
        check(f'unit: {f} tests/failures/errors', int(t.get('failures')) == 0 and int(t.get('errors')) == 0
              and int(t.get('tests')) > 0, f'tests={t.get("tests")} failures={t.get("failures")} errors={t.get("errors")}')


# ------------------------------------------------------------------ cluster
def load(d):
    P = f'{R}/cluster/{d}'
    rows = []
    with open(P + '/samples.csv') as f:
        rd = csv.DictReader(f)
        for r in rd:
            rows.append({k: (int(v) if v not in ('', None) else None) for k, v in r.items()})
    summ = open(P + '/summary.txt').read()
    js = lambda pat: [ast.literal_eval(m) for m in re.findall(pat + r' (\{.*\})', summ)]   # the Python repr the run printed
    sr = js(r'S result:')
    if sr:
        bulk = sr[0]
    else:   # the lifetime ended before the bulk client returned (B1): bulk start from session.log (local MDT clock)
        os.environ['TZ'] = 'America/Denver'; time.tzset()
        m = re.search(r'^\[(\S+ \S+)\] S: ', open(P + '/session.log').read(), re.M)
        bulk = {'ms_start': int(time.mktime(time.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')) * 1000), 'ok': None,
                'n': None, 'err': None, 'lat_mean_ms': None, 'lat_p99_ms': None, 'returned': False}
    big = js(r'L write \d+:')
    xs = js(r'X write \(17 MiB\):')
    x = xs[0] if xs else {'result': 'not reached', 'why': ''}
    tr = {}
    for l in open(P + '/mss.trace', errors='replace'):
        k = l.split(' ', 1)[0]
        kv = dict(re.findall(r'(\w+)=(\S+)', l))
        kv['slab'] = 'HintsBuffer.create' in l
        tr.setdefault(k, []).append(kv)
    printed = {}
    m = re.search(r'delta at end: direct_used ([+-]\d+), direct_count ([+-]\d+), rss ([+-]\d+), total_hints ([+-]\d+)', summ)
    if m:
        printed = {'direct': int(m.group(1)), 'rss': int(m.group(3)), 'hints': int(m.group(4))}
    return {'rows': rows, 'bulk': bulk, 'big': big, 'x': x, 'tr': tr, 'printed': printed, 'summary': summ}


lt = {}
for d in sorted(os.listdir(R + '/cluster')):
    if re.match(r'^(OFF|D|M4|M32|B1)-\d$', d) and os.path.exists(f'{R}/cluster/{d}/samples.csv'):
        lt[d] = load(d)
print('lifetimes:', sorted(lt))

rec = {}
for d, L in lt.items():
    arm = d.split('-')[0]
    rows, tr = L['rows'], L['tr']
    t0 = L['bulk']['ms_start']
    base = [r for r in rows if r['ms'] < t0][-1]
    end = rows[-1]
    created = tr.get('created', [])
    pre = [c for c in created if int(c['ms']) < t0]
    post = [c for c in created if int(c['ms']) >= t0]
    after = [r for r in rows if r['ms'] >= t0]
    peak = max(r['direct_used'] for r in after)
    alive = sum(r['b_alive'] for r in after)
    dd = end['direct_used'] - base['direct_used']
    drss = end['rss'] - base['rss']
    dh = end['total_hints'] - base['total_hints']
    rec[d] = {'arm': arm, 'dd': dd, 'dpeak': peak - base['direct_used'], 'drss': drss, 'dh': dh, 'pre': len(pre),
              'post': len(post), 'k': len(created), 'sizes': sorted({int(c['size']) for c in created}),
              'maxs': sorted({int(c['max']) for c in created}), 'bulk': L['bulk'],
              'slow': [int(s['us']) for s in tr.get('slowhint', [])], 'waiting': len(tr.get('waiting', [])),
              'closed': tr.get('closed', []), 'x': L['x'], 'big': L['big'],
              'slab_direct': sum(1 for x in tr.get('direct', []) if x['slab'])}
    r = rec[d]
    check(f'{d}: own end delta agrees with the run script (direct, rss, hints)', not L['printed'] or
          L['printed'] and abs(dd - L['printed']['direct']) <= 1 * MIB and abs(dh - L['printed']['hints']) == 0,
          f'mine direct {dd:+d} hints {dh:+d}; printed {L["printed"]}')
    check(f'{d}: B down for the whole workload (alive samples after the bulk start)', alive == 0, f'{alive}')
    if arm == 'B1':
        # MAX_HINT_BUFFERS=1: the run did not finish (results §3/§4): read the stall from the raw files
        last = rows[-1]
        stuck = [q for q in after if q['total_hints'] == last['total_hints']]
        jst = open(f'{R}/cluster/{d}/A-jstack-deadlock.txt').read()
        blocks = re.split(r'\n\n', jst)
        in_take = [b for b in blocks if 'LinkedBlockingQueue.take' in b and 'HintsBufferPool.switchCurrentBuffer' in b]
        waiting_lock = [b for b in blocks if 'HintsBufferPool' in b and 'waiting to lock' in b]
        hwe = [b for b in blocks if b.startswith('"HintsWriteExecutor') ]
        hwe_idle = all('FlushBufferTask' not in b and 'HintsWriter' not in b for b in hwe)
        tp = open(f'{R}/cluster/{d}/A-tpstats-deadlock.txt').read()
        ms = re.search(r'^MutationStage\s+(\d+)\s+(\d+)\s+(\d+)', tp, re.M)
        r.update({'stall_hints': last['total_hints'], 'stall_secs': (last['ms'] - stuck[0]['ms']) / 1000, 'in_take': len(in_take),
                  'waiting_lock': len(waiting_lock), 'hwe_idle': hwe_idle, 'mstage': ms.groups() if ms else None,
                  'offers': len(tr.get('offer', []))})
        check(f'{d}: one slab, made before the bulk start, none after', len(created) == 1 and len(post) == 0 and
              r['sizes'] == [32 * MIB] and r['maxs'] == [1], f'{len(created)} ({len(pre)} pre), max {r["maxs"]}')
        check(f'{d}: one writer at take() (waiting line), no slab ever offered back', r['waiting'] == 1 and r['offers'] == 0,
              f'waiting {r["waiting"]}, offer {r["offers"]}')
        check(f'{d}: TotalHints stopped ({last["total_hints"]}) for the rest of the lifetime', r['stall_secs'] > 300,
              f'flat for {r["stall_secs"]:.0f} s')
        check(f'{d}: thread dump: 1 thread in take() inside switchCurrentBuffer, the others blocked on the pool, '
              f'HintsWriteExecutor idle', len(in_take) == 1 and len(waiting_lock) >= 1 and hwe_idle,
              f'in take {len(in_take)}, waiting to lock {len(waiting_lock)}, executor idle {hwe_idle}, MutationStage '
              f'active/pending/completed {r["mstage"]}')
        continue
    check(f'{d}: bulk all acknowledged', r['bulk']['ok'] == r['bulk']['n'] and r['bulk']['err'] == 0,
          f'{r["bulk"]["ok"]}/{r["bulk"]["n"]}')
    check(f'{d}: slab allocations in the direct trace = created lines', r['slab_direct'] == r['k'], f'{r["slab_direct"]} vs {r["k"]}')
    if arm == 'OFF':
        check(f'{d}: control: no slab after the bulk start, TotalHints +0', len(post) == 0 and dh == 0,
              f'post {len(post)}, pre {len(pre)}, hints {dh:+d}')
        continue
    slab, kmax = SLAB[arm], KMAX[arm]
    check(f'{d}: hints written >= bulk n', dh >= r['bulk']['n'], f'{dh}')
    check(f'{d}: every slab has the predicted size and max', r['sizes'] == [slab] and r['maxs'] == [kmax],
          f'sizes {r["sizes"]} max {r["maxs"]}')
    check(f'{d}: slab count <= MAX_HINT_BUFFERS', 1 <= r['k'] <= kmax, f'{r["k"]} ({len(pre)} before the bulk start)')
    cl = r['closed']
    badc = [c for c in cl if not (int(c['prev']) >= 0 and int(c['prev']) + int(c['total']) > int(c['cap']) and int(c['cap']) == slab)]
    fills = sum(1 for c in cl if int(c['prev']) <= int(c['cap']))
    check(f'{d}: line 190 true branch: every closed line prev + total > cap = slab', cl and not badc,
          f'{len(cl)} lines, {len(badc)} bad, {fills} fills')
    r['fills'] = fills
    # 17 MiB write: which guard
    xw = r['x']['why']
    r['x_guard'] = ('native frame limit (Request is too big)' if 'Request is too big' in xw else
                    'max_mutation_size (validateSize)' if re.search(r'[Mm]utation.*too large|MutationExceeded', xw) else
                    'accepted' if r['x']['result'] == 'ok' else 'other: ' + xw[:80])

# cross-arm
off = [v for k, v in rec.items() if v['arm'] == 'OFF'][0]
print('\nlifetime | slabs (pre) | literal arm-OFF MiB | pool (incl. pre) MiB | peak MiB | RSS arm-OFF+pre MiB | hints | '
      'lat mean/p99 ms | slow hints n/max us | waiting | fills | 17 MiB')
for d, r in sorted(rec.items()):
    if r['arm'] == 'OFF':
        print(f'{d} | {r["k"]} ({r["pre"]}) | control: direct {r["dd"] / MIB:+.2f}, peak {r["dpeak"] / MIB:+.2f}, rss '
              f'{r["drss"] / MIB:+.2f} | | | | {r["dh"]} | {r["bulk"]["lat_mean_ms"]}/{r["bulk"]["lat_p99_ms"]} | '
              f'{len(r["slow"])}/{max(r["slow"], default=0)} | {r["waiting"]} | | {r["x"]["result"]}: {r["x"]["why"][:60]}')
        continue
    slab = SLAB[r['arm']]
    r['lit'] = r['dd'] - off['dd']
    r['pool'] = r['lit'] + r['pre'] * slab
    r['ppeak'] = r['dpeak'] - off['dpeak'] + r['pre'] * slab
    r['prss'] = r['drss'] - off['drss'] + r['pre'] * slab
    print(f'{d} | {r["k"]} ({r["pre"]}) | {r["lit"] / MIB:.2f} | {r["pool"] / MIB:.2f} | {r["ppeak"] / MIB:.2f} | '
          f'{r["prss"] / MIB:.2f} | {r["dh"]} | {r["bulk"]["lat_mean_ms"]}/{r["bulk"]["lat_p99_ms"]} | '
          f'{len(r["slow"])}/{max(r["slow"], default=0)} | {r["waiting"]} | {r.get("fills", "-")} | {r.get("x_guard", r["x"]["result"])}')
print()
for d, r in sorted(rec.items()):
    if r['arm'] == 'OFF':
        continue
    slab, kmax = SLAB[r['arm']], KMAX[r['arm']]
    check(f'{d}: pool direct in [slab - B, kmax x slab + B] (B3f)', slab - BAND <= r['pool'] <= kmax * slab + BAND,
          f'{r["pool"] / MIB:.2f} MiB')
    check(f'{d}: peak <= kmax x slab + B (B3g row 2 excluded)', r['ppeak'] <= kmax * slab + BAND, f'{r["ppeak"] / MIB:.2f} MiB')
    check(f'{d}: pool = slabs x slab within B (no growth past the slabs)', abs(r['pool'] - r['k'] * slab) <= BAND,
          f'{r["pool"] / MIB:.2f} vs {r["k"] * slab / MIB:.0f} MiB')
    if r['arm'] == 'B1':
        print(f'NOTE {d}: RSS (arm - OFF + pre) {r["prss"] / MIB:.2f} MiB at the stall (not comparable: the workload never finished)')
    else:
      check(f'{d}: RSS within 25 % of the pool direct (B3f bullet 5)', abs(r['prss'] - r['pool']) <= 0.25 * r['pool'],
          f'rss {r["prss"] / MIB:.2f} vs {r["pool"] / MIB:.2f} MiB')
    if r['arm'] in ('D', 'M4') or (r['arm'] == 'B1' and r['x']['result'] != 'not reached'):
        check(f'{d}: 17 MiB write refused, no hint (R2: write fails, no hint)', r['x']['result'] == 'err', r['x_guard'])
ds = [r for r in rec.values() if r['arm'] == 'D']
for d, r in sorted(rec.items()):
    if r['arm'] == 'M4':
        lo, hi = min(v['pool'] for v in ds) - BAND, max(v['pool'] for v in ds) + BAND
        check(f'{d}: same as default (B3f bullet 2, B3g row 3 excluded)', lo <= r['pool'] <= hi,
              f'{r["pool"] / MIB:.2f} in [{lo / MIB:.2f}, {hi / MIB:.2f}]')
        check(f'{d}: 8 MiB writes (recorded): outcome', True, str([b['result'] + ' ' + b['why'][:70] for b in r['big']][:1]))
    if r['arm'] == 'M32':
        dps = statistics.mean(v['pool'] / v['k'] for v in ds)
        ratio = (r['pool'] / r['k']) / dps
        check(f'{d}: one-slab step doubles (B3f bullet 3)', 1.8 <= ratio <= 2.2, f'ratio {ratio:.3f}')
        check(f'{d}: pool in [64, 192] MiB +- B (B3g row 4 excluded)', 64 * MIB - BAND <= r['pool'] <= 192 * MIB + BAND,
              f'{r["pool"] / MIB:.2f}')
    if r['arm'] == 'B1':
        check(f'{d}: one slab (R1 row 1)', r['k'] == 1 and abs(r['pool'] - 32 * MIB) <= BAND, f'{r["k"]}, {r["pool"] / MIB:.2f} MiB')
        check(f'{d}: writers waited at take()', r['waiting'] > 0, f'{r["waiting"]}')
        check(f'{d}: hint write latency rises (slow writes n and max above every default run)',
              all(len(r['slow']) > len(v['slow']) and max(r['slow'], default=0) > max(v['slow'], default=0) for v in ds),
              f'B1 {len(r["slow"])}/{max(r["slow"], default=0)} vs D {[(len(v["slow"]), max(v["slow"], default=0)) for v in ds]}')
        check(f'{d}: differs from default by more than B (R1 row 2 excluded)', all(abs(r['pool'] - v['pool']) > BAND for v in ds),
              f'{r["pool"] / MIB:.2f} vs {[round(v["pool"] / MIB, 2) for v in ds]}')
if len(ds) == 2:
    print(f'default repeat spread: {abs(ds[0]["pool"] - ds[1]["pool"]) / MIB:.2f} MiB')
print(f'\nSELFCHECK ok {res["ok"]} fail {res["fail"]}')
