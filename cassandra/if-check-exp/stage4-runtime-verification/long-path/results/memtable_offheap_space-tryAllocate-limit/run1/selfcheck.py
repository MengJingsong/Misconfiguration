#!/usr/bin/env python3
"""Independent self-check of run 1, memtable_offheap_space-tryAllocate-limit (stage-4 README, "Self-check").

usage (on the node): python3 selfcheck.py [~/stage4-logs/mos]

Re-parses the raw files of every run directory with code of its own (it does not import cluster-run.py or
ledger.py): system.log, debug.log, cassandra.diff, jvm-args.txt, thread dumps, escape-hatch.txt, ledger.txt,
rss.csv, nmt-*.txt, session.log (stress start time) and the unit tier's NativePoolTest.out / TEST xml. Discards
are paired by allocator id over the whole ledger (not by the discard..discarded bracket ledger.py uses).
Prints one "ok"/"FAIL" line per check and the cross-run figures; exit 1 if any check fails."""
import glob, os, re, sys

MIB = 1048576
ROOT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/stage4-logs/mos')
VALUES = ['128', '256', '512', 'default']
ARMS = ['small', 'oversize']
STASH = 8 * sum(8192 << i for i in range(8))
results, fails = {}, []


def check(name, cond, detail=''):
    print(f'{"ok  " if cond else "FAIL"} {name}' + (f'  {detail}' if detail != '' else ''))
    if not cond:
        fails.append(name)
    return cond


def read(path):
    with open(path, errors='replace') as f:
        return f.read()


def ms_of_syslog(line):
    # system.log lines are UTC: "INFO  [thread] 2026-10-14T00:48:12,389 ..."
    import datetime
    m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3})', line)
    if not m:
        return None
    t = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return int(t.timestamp() * 1000) + int(m.group(2))


def unit():
    d = f'{ROOT}/unit'
    out = read(f'{d}/NativePoolTest.out')
    vals = dict(re.findall(r'^STAGE4 (\S+ \S+)=(.*)$', out, re.M))
    want = {'1 pool.offHeap.used': '100', '2 waiter.state': 'WAITING', '2 parked_in_SubAllocator.allocate': '1',
            '2 future_get_300ms_timed_out': '1', '3 pool.offHeap.used_after_2s': '100', '3 still_parked': '1',
            '4 woken_allocation_returned_peer': '1', '4 pool.offHeap.used': '100', '5 forced_allocation_returned_peer': '1',
            '5 pool.offHeap.used': '110', '6 pool.offHeap.used_after_discard': '0'}
    for k, v in want.items():
        check(f'unit: NativePoolTest {k} = {v}', vals.get(k) == v, vals.get(k))
    check('unit: waiter frame is SubAllocator.allocate:195', 'MemtableAllocator$SubAllocator.allocate:195' in vals.get('2 waiter.frames', ''))
    check('unit: no MISMATCH', 'MISMATCH' not in out)
    for t in ('NativeAllocatorTest', 'NativePoolTest'):
        x = read(f'{d}/TEST-org.apache.cassandra.utils.memory.{t}.xml')
        m = re.search(r'<testsuite[^>]*errors="(\d+)"[^>]*failures="(\d+)"[^>]*tests="(\d+)"', x)
        check(f'unit: {t} xml 0 errors, 0 failures, >=1 test', bool(m) and m.group(1) == '0' and m.group(2) == '0' and int(m.group(3)) >= 1,
              m.groups() if m else 'no testsuite line')


def ledger(path, t_idle, t0, t1):
    live, L, Lidle, maxL, maxms = {}, 0, 0, 0, None
    owns, freed, nreg, unmatched, mallocs = {}, {}, {}, 0, 0
    with open(path) as f:
        for line in f:
            p = line.split()
            kv = dict(x.split('=', 1) for x in p[1:] if '=' in x)
            ms = int(kv['ms'])
            if p[0] == 'malloc':
                mallocs += 1
                L += int(kv['cap']) - live.get(kv['peer'], 0)
                live[kv['peer']] = int(kv['cap'])
            elif p[0] == 'free':
                if kv['peer'] in live:
                    L -= live.pop(kv['peer'])
                else:
                    unmatched += 1
                if kv.get('site') == 'discard':
                    freed[kv['alloc']] = freed.get(kv['alloc'], 0) + int(kv['cap'])
                    nreg[kv['alloc']] = nreg.get(kv['alloc'], 0) + 1
            elif p[0] == 'discard':
                owns.setdefault(kv['alloc'], []).append(int(kv['owns']))
            if ms <= t_idle:
                Lidle = L
            if t0 <= ms <= t1 and L > maxL:
                maxL, maxms = L, ms
    pairs = [(a, o[0], freed.get(a, 0), nreg.get(a, 0)) for a, o in owns.items() if len(o) == 1]
    dup = [a for a, o in owns.items() if len(o) > 1]
    return dict(Lidle=Lidle, maxL=maxL, maxms=maxms, pairs=pairs, dup=dup, unmatched=unmatched, mallocs=mallocs, Lend=L)


def run(label, arm):
    d = f'{ROOT}/{label}-{arm}'
    name = f'{label}-{arm}'
    if not os.path.isdir(d):
        check(f'{name}: run directory exists', False, d); return
    r = {}
    floor = label == 'floor256'
    syslog, dbg = read(f'{d}/system.log'), read(f'{d}/debug.log')
    diff = [l for l in read(f'{d}/cassandra.diff').splitlines() if l.startswith('+') and not l.startswith('+++')]
    knob = {'128': 128, '256': 256, '512': 512, 'cleanup256': 256}.get(label)
    exp = {f'+memtable_heap_space: {256 if floor else 2048}MiB',
           f'+memtable_allocation_type: {"unslabbed_heap_buffers" if floor else "offheap_objects"}'}
    if knob:
        exp.add(f'+memtable_offheap_space: {knob}MiB')
    if label != 'cleanup256':
        exp.add('+memtable_cleanup_threshold: 0.99')
    check(f'{name}: yaml diff is exactly the 9b lines', set(diff) == exp, sorted(diff))
    m = re.search(r'Global memtable off-heap threshold is enabled at (\d+)MiB', syslog)
    lim = int(m.group(1)) if m else None
    if not floor:
        check(f'{name}: off-heap limit in system.log = {knob or "about 1024"} MiB',
              lim == knob if knob else (lim is not None and 1000 <= lim <= 1024), lim)
        check(f'{name}: debug.log "Memtables allocating with off-heap objects"', 'Memtables allocating with off-heap objects' in dbg)
    else:
        check(f'{name}: debug.log "Memtables allocating with on-heap buffers"', 'Memtables allocating with on-heap buffers' in dbg)
    LIMIT = (lim or 0) * MIB
    r['limit'] = LIMIT
    args = read(f'{d}/jvm-args.txt').split('\n')
    check(f'{name}: JVM -Xms4G -Xmx4G, NMT, Byteman', all(a in args for a in ('-Xms4G', '-Xmx4G', '-XX:NativeMemoryTracking=summary'))
          and any('byteman-4.0.20.jar' in a and 'region-ledger.btm' in a for a in args))
    # stress start and the run's windows, from session.log and summary.txt's own window line
    win = re.search(r'windows \(ms\): T_idle=(\d+) T_A0=(\d+) T_A1=(\d+) T_C0=(\d+) T_STOP=(\d+)', read(f'{d}/summary.txt'))
    t_idle, t_a0, t_a1, t_c0, t_stop = (int(x) for x in win.groups())
    sess = read(f'{d}/session.log')
    check(f'{name}: session.log shows the stress start at T_A0', f'(T_A0={t_a0})' in sess)
    # flush lines (system.log, UTC) — limit flushes of keyspace1 inside the run window
    lf = [l for l in syslog.splitlines() if re.search(r'Enqueuing flush of keyspace1\.standard1, Reason: MEMTABLE_LIMIT', l)]
    first = lf[0] if lf else ''
    fm = re.search(r'([0-9.]+)(KiB|MiB|GiB) \((\d+)%\) off-heap', first)
    unit = {'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024}
    r['first_offheap_MiB'] = float(fm.group(1)) * unit[fm.group(2)] if fm else None
    r['first_pct'] = int(fm.group(3)) if fm else None
    r['limit_flushes'] = len(lf)
    hp = [float(x) for x in re.findall(r'([0-9.]+)(?:KiB|MiB|GiB) \(\d+%\) on-heap', first)]
    if not floor:
        check(f'{name}: >= 4 MEMTABLE_LIMIT flushes of keyspace1.standard1', len(lf) >= 4, len(lf))
        ut = [float(x) for x in re.findall(r'Used total: [0-9.]+/([0-9.]+)', syslog)]
        r['max_used_total'] = max(ut) if ut else None
        check(f'{name}: no off-heap Used total above 1.00', not ut or max(ut) <= 1.0, max(ut) if ut else None)
        if label != 'cleanup256':
            check(f'{name}: first keyspace1 limit flush off-heap Usage >= 97 %', (r['first_pct'] or 0) >= 97, r['first_pct'])
    # waits: thread dumps (raw)
    dumps = sorted(glob.glob(f'{d}/threaddump-B*.txt'))
    fr = [read(x).count('MemtableAllocator.java:195') for x in dumps]
    r['dump_frames'] = fr
    check(f'{name}: writers seen parked at MemtableAllocator.java:195 in a B thread dump', any(f > 0 for f in fr), fr)
    # escape-hatch trace (raw)
    n = s = other = 0
    if os.path.exists(f'{d}/escape-hatch.txt'):
        for l in open(f'{d}/escape-hatch.txt'):
            mm = re.match(r'forced=(\d+) limit=(\d+) ms=(\d+)', l)
            if mm and int(mm.group(2)) == LIMIT and not floor:
                n += 1; s += int(mm.group(1))
            elif mm:
                other += 1
    r['F'] = s; r['F_calls'] = n
    # RssAnon (raw)
    rows = [tuple(int(x) for x in l.split(',')) for l in read(f'{d}/rss.csv').splitlines()[1:] if l.strip()]
    idle = [x for x in rows if x[0] <= t_idle][-1][1]
    peak = max(x[1] for x in rows if t_a0 <= x[0] <= t_stop)
    r['d_rss'] = (peak - idle) * 1024
    # NMT Other (raw)
    def nmt_other(tag):
        f = f'{d}/nmt-{tag}.txt'
        mm = re.search(r'-\s+Other \(reserved=\d+KB, committed=(\d+)KB', read(f)) if os.path.exists(f) else None
        return int(mm.group(1)) * 1024 if mm else None
    r['nmt_other_idle'], r['nmt_other_endB'] = nmt_other('idle'), nmt_other('endB')
    if floor:
        check(f'{name}: ledger has no malloc line', not os.path.exists(f'{d}/ledger.txt') or 'malloc' not in read(f'{d}/ledger.txt'))
        results[name] = r
        return
    lg = ledger(f'{d}/ledger.txt', t_idle, t_a0, t_stop)
    check(f'{name}: ledger has malloc lines', lg['mallocs'] > 0, lg['mallocs'])
    check(f'{name}: ledger frees all match live peers', lg['unmatched'] == 0, lg['unmatched'])
    check(f'{name}: allocator ids unique per discard', not lg['dup'], len(lg['dup']))
    big = [p for p in lg['pairs'] if p[1] >= 8 * MIB]
    out = [p for p in lg['pairs'] if not (0 <= p[2] - p[1] <= MIB + 0.002 * p[1])]
    check(f'{name}: per discard 0 <= P_m - A_m <= 1 MiB + 0.002 A_m ({len(lg["pairs"])} discards, {len(big)} >= 8 MiB)', not out,
          [(p[1], p[2]) for p in out][:5])
    r['gaps'] = [p[2] - p[1] for p in big]
    r['ratio'] = [p[2] / p[1] for p in big]
    r['A_m_max'] = max((p[1] for p in big), default=None)
    dl = lg['maxL'] - lg['Lidle']
    lo, hi = 0.99 * LIMIT - lg['Lidle'] - MIB, LIMIT + s + 19 * MIB + 0.002 * LIMIT
    r.update(Lidle=lg['Lidle'], maxL=lg['maxL'], dL=dl, lo=lo, hi=hi)
    check(f'{name}: node-wide {lo / MIB:.2f} <= max L - L_idle = {dl / MIB:.2f} <= {hi / MIB:.2f} MiB', lo <= dl <= hi)
    # A_m never above limit + forced bytes of the run; how far above the limit it went
    check(f'{name}: every A_m <= limit + F', all(p[1] <= LIMIT + s for p in lg['pairs']), r['A_m_max'])
    over = [p[1] - LIMIT for p in lg['pairs'] if p[1] > LIMIT]
    r['over'] = (len(over), max(over) if over else 0)
    # live keyspace1 memtables at the moment of max L: limit flushes enqueued by then (system.log, UTC ms),
    # less memtables of >= 8 MiB already discarded (ledger), plus the current one
    enq = [ms_of_syslog(l) for l in syslog.splitlines() if 'Enqueuing flush of keyspace1.standard1' in l]
    disc_ms = []
    for line in open(f'{d}/ledger.txt'):
        if line.startswith('discard ') and int(re.search(r'owns=(\d+)', line).group(1)) >= 8 * MIB:
            disc_ms.append(int(re.search(r'ms=(\d+)', line).group(1)))
    r['live_at_maxL'] = sum(1 for x in enq if x is not None and x <= lg['maxms']) - sum(1 for x in disc_ms if x <= lg['maxms']) + 1
    results[name] = r


def main():
    unit()
    for arm in ARMS:
        for v in VALUES:
            run(v, arm)
    run('cleanup256', 'small')
    for arm in ARMS:
        run('floor256', arm)
    print('\ncross-run figures')
    for arm in ARMS:
        rows = [(v, results.get(f'{v}-{arm}')) for v in VALUES]
        rows = [(v, r) for v, r in rows if r and r.get('maxL') is not None]
        if len(rows) < 4:
            check(f'{arm}: all four values present', False); continue
        lims = [r['limit'] for _, r in rows]
        dls = [r['dL'] for _, r in rows]
        firsts = [r['first_offheap_MiB'] for _, r in rows]
        check(f'{arm}: max L - L_idle increases with the limit', all(a < b for a, b in zip(dls, dls[1:])), [round(x / MIB, 1) for x in dls])
        check(f'{arm}: first limit flush off-heap Usage increases with the limit', all(a < b for a, b in zip(firsts, firsts[1:])), firsts)
        fl = results.get(f'floor256-{arm}')
        for v, r in rows:
            gaps = r['gaps']
            print(f'  {arm} {v}: limit {r["limit"] / MIB:.0f} MiB; first flush {r["first_offheap_MiB"]} MiB ({r["first_pct"]} %); '
                  f'limit flushes {r["limit_flushes"]}; max L - L_idle {r["dL"] / MIB:.2f} MiB = {r["dL"] / r["limit"]:.4f} x limit '
                  f'(bounds {r["lo"] / MIB:.2f}..{r["hi"] / MIB:.2f}); P_m - A_m {min(gaps) / MIB:.3f}..{max(gaps) / MIB:.3f} MiB, '
                  f'P_m/A_m {min(r["ratio"]):.5f}..{max(r["ratio"]):.5f} over {len(gaps)} discards >= 8 MiB; F {r["F"]} B in {r["F_calls"]} calls; '
                  f'max dRssAnon {r["d_rss"] / MIB:.1f} MiB; NMT Other idle->endB {r["nmt_other_idle"]}->{r["nmt_other_endB"]}; dumps {r["dump_frames"]}; '
                  f'A_m above limit: {r["over"][0]} memtables, max excess {r["over"][1]} B (F {r["F"]}); live keyspace1 memtables at max L: {r["live_at_maxL"]}')
            if fl:
                lhs, rhs = r['d_rss'], r['dL'] + fl['d_rss'] + 64 * MIB
                print(f'    process cross-check: max dRssAnon {lhs / MIB:.1f} MiB vs max dL + floor dRssAnon ({fl["d_rss"] / MIB:.1f}) + 64 = {rhs / MIB:.1f} MiB -> '
                      f'{"within" if lhs <= rhs else "ABOVE"}')
    c = results.get('cleanup256-small')
    if c:
        print(f'  cleanup256-small: first flush {c["first_offheap_MiB"]} MiB ({c["first_pct"]} %), dumps {c["dump_frames"]}, max L - L_idle {c["dL"] / MIB:.2f} MiB '
              f'(9a bound for the 0.99 runs {c["hi"] / MIB:.2f}); live keyspace1 memtables at max L: {c["live_at_maxL"]}; limit flushes {c["limit_flushes"]}')
    for arm in ARMS:
        f = results.get(f'floor256-{arm}')
        if f:
            print(f'  floor256-{arm}: max dRssAnon {f["d_rss"] / MIB:.1f} MiB; NMT Other idle->endB {f["nmt_other_idle"]}->{f["nmt_other_endB"]}; dumps {f["dump_frames"]}')
    print(f'\n{len(fails)} checks failed' + (': ' + '; '.join(fails) if fails else ''))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
