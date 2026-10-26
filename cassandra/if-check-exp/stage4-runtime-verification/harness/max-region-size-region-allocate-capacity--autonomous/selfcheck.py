#!/usr/bin/env python3
"""Independent self-check (step 4) of max-region-size-region-allocate-capacity--autonomous. Re-parses the RAW files (unit .out files, jmx.csv,
rss.csv, system.log, big.out, phases.json) without importing cluster-run.py or reading the probe's own 'STAGE4 check' lines; the region-size rule is
re-implemented here from NativeAllocator.java:144-168 (not copied from the probe). usage: selfcheck.py [run] (default run1). Prints one line per
relation; 'BAD' marks a relation that does not hold. Exit 0."""
import glob, json, os, re, sys

RUN = sys.argv[1] if len(sys.argv) > 1 else 'run1'
LG = os.path.expanduser(f'~/s4-b7-mr-logs/{RUN}')
MIB = 1 << 20
bad = 0


def say(ok, msg):
    global bad
    bad += (not ok)
    print(('ok  ' if ok else 'BAD ') + msg)


def kv(path):
    d = {}
    for l in open(path, errors='replace'):
        m = re.match(r'STAGE4 reading (\w+)=(.*)$', l.strip())
        if m:
            d[m.group(1)] = m.group(2)
    return d


def replay(n, s, maxr):
    """NativeAllocator.allocate/trySwapRegion: region sizes for n allocations of s bytes with this MAX_REGION_SIZE"""
    if s > 131072:
        return n * s, n, s
    regions, cap, cur_cap, used, mx = 0, 0, None, 0, 0
    for _ in range(n):
        if cur_cap is None or used + s > cur_cap:
            size = 8192 if cur_cap is None else cur_cap * 2
            if s > size:
                size = (1 << (s.bit_length() - 1)) << 3
            size = min(maxr, size)
            cur_cap, used = size, 0
            regions += 1; cap += size; mx = max(mx, size)
        used += s
    return cap, regions, mx


print('== unit tier (raw readings recomputed)')
fills = {}
for f in sorted(glob.glob(f'{LG}/unit/fill-*.out')):
    m = re.search(r'fill-(\w+)-(\d+)-(\d+)\.out', f)
    v, n, s = m.group(1), int(m.group(2)), int(m.group(3))
    d = kv(f)
    maxr = int(d['MAX_REGION_SIZE'])
    cap, reg, mx = int(d['capacity_sum']), int(d['regions']), int(d['max_capacity'])
    used, owns = int(d['used']), int(d['owns'])
    rcap, rreg, rmx = replay(n, s, maxr)
    fills[(v, n, s)] = dict(cap=cap, reg=reg, mx=mx, used=used, owns=owns, rss=int(d['rss_delta']), maxr=maxr)
    say(used == n * s and owns == n * s, f'{v} n={n} s={s}: charged used={used} owns={owns} == n*s')
    say((cap, reg, mx) == (rcap, rreg, rmx), f'{v} n={n} s={s}: cap/regions/max {cap}/{reg}/{mx} == independent replay {rcap}/{rreg}/{rmx} (MAX_REGION_SIZE {maxr})')
    exp_max = maxr if s <= 131072 else s
    say(mx == exp_max, f'{v} n={n} s={s}: max capacity {mx} == {"constant" if s <= 131072 else "s (oversize)"} {exp_max}')
    say(int(d['used_after_discard']) == 0, f'{v} n={n} s={s}: charge released by setDiscarded (used_after_discard={d["used_after_discard"]})')
    # RssAnon is an informational cross-check (B2d 'optional'), not a B2f prediction: printed, never pass/fail
    print(f'   info {v} n={n} s={s}: RssAnon delta {int(d["rss_delta"])/MIB:.1f} MiB = {int(d["rss_delta"])/used:.3f} x charged, {int(d["rss_delta"])/cap:.3f} x capacity')
exp = {'stock': 1 << 20, 'm256': 256 << 10, 'm4096': 4 << 20}  # print order: stock (1 MiB), m256, m4096
for (v, n, s), r in fills.items():
    if v in exp:
        say(r['maxr'] == exp[v], f'{v}: loaded MAX_REGION_SIZE {r["maxr"]} == tree edit {exp[v]}')
print('-- across builds, same n and s (the knob axis)')
for n, s in ((2000000, 100), (1000, 100000), (1000, 131072), (1000, 131073)):
    rows = {v: fills[(v, n, s)] for v in exp if (v, n, s) in fills}
    if len(rows) < 3:
        print(f'   n={n} s={s}: only {sorted(rows)} present'); continue
    say(len({r['owns'] for r in rows.values()}) == 1, f'n={n} s={s}: owns identical across builds: {[rows[v]["owns"] for v in exp]}')
    caps = [rows[v]['cap'] for v in exp]
    sl = [round(100 * (rows[v]['cap'] - rows[v]['owns']) / rows[v]['owns'], 2) for v in exp]
    print(f'   n={n} s={s}: capacity sums (build order 1M, 256K, 4M) {caps}; slack % {sl}; regions {[rows[v]["reg"] for v in exp]}; max capacity {[rows[v]["mx"] for v in exp]}')
    if s == 100:
        say(all(abs(c - caps[1]) / caps[1] <= 0.02 for c in caps), f's=100: sum of capacities within 2 % of the 1 MiB value across a 16x change of the constant')
for f in sorted(glob.glob(f'{LG}/unit/threads-*.out')):
    d = kv(f)
    say(int(d['used']) == int(d['n']) * 100 and int(d['owns']) == int(d['used']), f'{os.path.basename(f)}: charged == n*s with 8 threads; stash {d.get("stash_nonempty")!r}, bytes {d.get("stash_bytes")}')
    say(all(int(x.split(':')[1]) <= 8 for x in d.get('stash_nonempty', '').split() if ':' in x), f'{os.path.basename(f)}: no stash class above 8 regions')
for f in sorted(glob.glob(f'{LG}/unit/limit-*.out')):
    d = kv(f)
    L, used, n = int(d['limit']), int(d['used']), int(d['n'])
    say(used <= L < used + 100000, f'{os.path.basename(f)}: non-blocking fill stops at the limit: used={used} L={L}')
    say(d.get('extra_state_2s') in ('WAITING', 'TIMED_WAITING'), f'{os.path.basename(f)}: extra non-blocking allocation parked ({d.get("extra_state_2s")})')
    say(d.get('blocking_writer_alive') == 'false' and int(d['used_after_blocking']) == used + 10 * 100000 and int(d['used_after_blocking']) > L,
        f'{os.path.basename(f)}: blocking group did not park and overshot: {d.get("used_after_blocking")} > {L}')
    say(d.get('extra_state_after_discard') == 'TERMINATED', f'{os.path.basename(f)}: parked allocation completes after discard ({d.get("extra_state_after_discard")})')
    say(int(d['capacity_sum']) >= used, f'{os.path.basename(f)}: sum of capacities {d["capacity_sum"]} >= charged')

print('== cluster tier (raw files recomputed)')
CL = f'{LG}/cluster'
res = {}
for a in ('m256', 'm256b', 'm256c', 'm1024', 'm1024b', 'm1024c', 'm4096', 'm4096b', 'm4096c', 'o128', 'o256'):
    p = f'{CL}/{a}/phases.json'
    if not os.path.exists(p):
        continue
    ph = json.load(open(p))
    L = ph['L'] * MIB
    w0, fl = ph['work_ms'], ph['flush_ms']
    off, blk = [], []
    for l in open(f'{CL}/{a}/jmx.csv').read().splitlines()[1:]:
        c = l.split(',')
        if len(c) == 5:
            try:
                t = int(c[0]); o = float(c[1]); b = float(c[3])
            except ValueError:
                continue
            if w0 <= t <= fl:
                off.append(o)
            if t >= ph['base_ms']:
                blk.append(b)
    rss = []
    for l in open(f'{CL}/{a}/rss.csv').read().splitlines()[1:]:
        c = l.split(',')
        if len(c) == 5 and c[1] and w0 <= int(c[0]) <= fl:
            rss.append(int(c[1]))
    flushes = {}
    for l in open(f'{CL}/{a}/system.log', errors='replace'):
        m = re.search(r'Enqueuing flush of ks\.t, Reason: (\w+)', l)
        if m:
            flushes[m.group(1)] = flushes.get(m.group(1), 0) + 1
    big = json.load(open(f'{CL}/{a}/big.out'))
    cmd = open(f'{CL}/{a}/session.log').read()
    r = dict(L=L, peak=max(off), rss_delta=max(rss) - ph['baseline']['RssAnon'], blocked=(blk[-1] - blk[0]) if blk else None, flushes=flushes, big=big, tree=ph['tree'])
    res[a] = r
    say(big.get('ok') == ph['big_n'] and big.get('err') == 0, f'{a}: client wrote {big.get("ok")} rows, errors {big.get("err")}')
    say(0.9 * L <= r['peak'] <= 1.05 * L, f'{a}: peak AllMemtablesOffHeapDataSize {r["peak"]/MIB:.1f} MiB in [0.9 L, 1.05 L] of {ph["L"]} MiB')
    say((r['blocked'] or 0) > 0 and sum(flushes.values()) >= 2 and flushes.get('MEMTABLE_LIMIT', 0) >= 1, f'{a}: BlockedOnAllocation +{r["blocked"]}, flushes {flushes}')
    say(r['rss_delta'] <= 1.3 * L, f'{a}: RssAnon peak delta {r["rss_delta"]/MIB:.1f} MiB <= 1.3 L ({1.3*ph["L"]:.0f} MiB)')
    print(f'   {a}: tree {r["tree"]}')
knob = [a for a in ('m256', 'm1024', 'm4096') if a in res]
if len(knob) == 3:
    pk = [res[a]['peak'] for a in knob]; rd = [res[a]['rss_delta'] for a in knob]; L = 64 * MIB
    say(max(pk) - min(pk) <= 0.05 * L, f'knob axis: peaks {[round(x/MIB,2) for x in pk]} MiB within 0.05 L ({0.05*64:.1f} MiB)')
    say(max(rd) - min(rd) <= 0.25 * L and max(rd) / min(rd) <= 1.3, f'knob axis: RssAnon deltas {[round(x/MIB,1) for x in rd]} MiB: spread {(max(rd)-min(rd))/MIB:.1f} MiB (<= 16), ratio {max(rd)/min(rd):.2f} (<= 1.3)')
if 'm1024' in res and 'm1024b' in res:
    a, b = res['m1024'], res['m1024b']
    print(f'   noise m1024 vs m1024b: peak {a["peak"]/MIB:.2f} / {b["peak"]/MIB:.2f} MiB, RssAnon delta {a["rss_delta"]/MIB:.1f} / {b["rss_delta"]/MIB:.1f} MiB')
sw = [a for a in ('m1024', 'o128', 'o256') if a in res]
if len(sw) == 3:
    pk = [res[a]['peak'] for a in sw]; rd = [res[a]['rss_delta'] for a in sw]
    say(pk[0] < pk[1] < pk[2], f'control sweep: peaks {[round(x/MIB,1) for x in pk]} MiB ordered 64 < 128 < 256')
    r2, r4 = rd[1] / rd[0], rd[2] / rd[0]
    say(1.5 <= r2 <= 2.5 and 3.0 <= r4 <= 5.0, f'control sweep: RssAnon-delta ratios 128/64 = {r2:.2f} (1.5-2.5), 256/64 = {r4:.2f} (3.0-5.0)')
# supplement (results 1.2, rules declared before its data): three repeats per build; "within noise" = spread of the means <= the largest within-build range
trip = {'256K': ('m256', 'm256b', 'm256c'), '1M': ('m1024', 'm1024b', 'm1024c'), '4M': ('m4096', 'm4096b', 'm4096c')}
if all(a in res for v in trip.values() for a in v):
    means, ranges, peaks = {}, {}, []
    for k, v in trip.items():
        x = [res[a]['rss_delta'] / MIB for a in v]
        means[k], ranges[k] = sum(x) / 3, max(x) - min(x)
        peaks += [res[a]['peak'] for a in v]
        print(f'   supplement {k}: RssAnon deltas {[round(y, 1) for y in x]} MiB, mean {means[k]:.1f}, range {ranges[k]:.1f}')
    spread = max(means.values()) - min(means.values())
    say(spread <= max(ranges.values()), f'supplement: spread of the three means {spread:.1f} MiB <= largest within-build range {max(ranges.values()):.1f} MiB (within noise)')
    say(max(means.values()) / min(means.values()) < 4, f'supplement: ratio of means {max(means.values())/min(means.values()):.2f} < 4 (not proportional to the 16x constant)')
    say(max(peaks) - min(peaks) <= 0.05 * 64 * MIB, f'supplement: all nine tracked peaks within {(max(peaks)-min(peaks))/MIB:.1f} MiB (<= 3.2 = 0.05 L)')
    # JVM-tracked growth (NMT total committed) is read from nmt.csv, independent of L and build
    for a in sorted(res):
        ph = json.load(open(f'{CL}/{a}/phases.json')); w0, fl = ph['work_ms'], ph['flush_ms']
        nm = [int(c[2]) for c in (l.split(',') for l in open(f'{CL}/{a}/nmt.csv').read().splitlines()[1:]) if len(c) == 3 and c[2] not in ('', 'None') and w0 <= int(c[0]) <= fl]
        if nm:
            print(f'   info {a}: NMT total committed peak delta {(max(nm) - ph["baseline_nmt"][1]) / MIB:.1f} MiB; RssAnon delta - tracked peak = {(res[a]["rss_delta"] - res[a]["peak"]) / MIB:.1f} MiB')
print(f'selfcheck {RUN}: BAD lines = {bad}')
