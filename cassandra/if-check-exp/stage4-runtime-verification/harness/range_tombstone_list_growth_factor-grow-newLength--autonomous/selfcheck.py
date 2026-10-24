#!/usr/bin/env python3
"""Independent self-check (stage-4 step 4) for the range_tombstone_list_growth_factor autonomous cases. It re-parses the RAW files
and does not import or reuse unit-analyze.py / cluster-analyze.py (different parsing: whitespace split, own simulation of the
growth expression, own histogram parser over the raw jcmd output).
usage: selfcheck.py unit <rtl-unit.txt> <junit-xml> | cluster <cluster-log-dir>
Prints 'CHECK n: <statement> -> HOLDS / DOES NOT HOLD (numbers)'."""
import collections, glob, json, math, os, re, sys

N = [0]
def chk(stmt, ok, num=''):
    N[0] += 1
    print(f'CHECK {N[0]}: {stmt} -> {"HOLDS" if ok else "DOES NOT HOLD"}' + (f' ({num})' if num else ''))


def grow_once(cap, f):               # RangeTombstoneList.growToFree, lines 683-686, done with floats/ints as Java does
    nl = int(math.ceil(float(cap) * f))
    if nl <= cap:
        nl = (cap * 3) // 2 + 1
    return nl


def kv(line):
    out = {}
    for tok in line.split(' ')[1:]:
        if '=' in tok:
            k, v = tok.split('=', 1); out[k] = v
    return out


if sys.argv[1] == 'unit':
    raw = open(sys.argv[2]).read().splitlines()
    xml = open(sys.argv[3]).read()
    chk('junit XML: one test, 0 failures, 0 errors', 'tests="1"' in xml and 'failures="0"' in xml and 'errors="0"' in xml, re.findall(r'<testsuite [^>]*>', xml)[0][:150])
    rows = [kv(l) | {'_k': l.split()[1].split('=')[1]} for l in raw if l.startswith('RTL ') and ' kind=' in l.split('\n')[0][:12]]
    # the kind is the first field
    rows = []
    for l in raw:
        if l.startswith('RTL '):
            d = kv(l); d['kind'] = l.split()[1].split('=', 1)[1]; rows.append(d)
    hdr = [l for l in raw if l.startswith('HEADER')][0]
    case = kv(hdr)['case']
    print(f'case {case}; {len(rows)} RTL rows; header: {hdr[:200]}')
    srt = [r for r in rows if r['kind'] in ('sorted', 'random')]
    # 1. recompute capacity after N adds by plain simulation (not by series), compare with lens/events/size
    bad = 0
    for r in srt:
        f, s, n = float(r['f']), int(r['s']), int(r['N'])
        cap, ev = s, 0
        for size in range(n):
            if size == cap:
                cap = grow_once(cap, f); ev += 1
        if not (int(r['size']) == n and set(r['lens'].split('/')) == {str(cap)} and int(r['events']) == ev):
            bad += 1
    chk('final capacity, growth-event count and size of every sorted/random run equal an independent simulation of lines 683-686', bad == 0, f'{len(srt)} runs, {bad} differ')
    # 2. series printed (up to 80 events) agrees with the simulation event by event
    bad = 0
    for r in srt:
        f, s, n = float(r['f']), int(r['s']), int(r['N'])
        got = [tuple(map(int, p.split(':'))) for p in r['series'].split(',') if p]
        cap, exp = s, []
        for size in range(n):
            if size == cap:
                cap = grow_once(cap, f); exp.append((size + 1, cap))
        if got != exp[:80]: bad += 1
    chk('printed growth series (first 80 events) equals the simulation event by event', bad == 0, f'{bad} differ')
    # 3. accounting arithmetic: unshared == (empty-list size - its four zero-length arrays) + boundary + array bytes; the 'empty' field is the
    #    unsharedHeapSize() of a list with four zero-length arrays (4 x 16 B headers), so the constant is -64 B
    diffs = collections.Counter(int(r['unshared']) - int(r['empty']) - int(r['boundary']) - int(r['arrays']) for r in srt)
    chk('unsharedHeapSize() == EMPTY_SIZE + boundaryHeapSize + array bytes in every run: unshared - empty - boundary - arrays is the same constant -64 B (the four zero-length arrays inside the empty list)', list(diffs) == [-64], str(dict(diffs)))
    # 4. double count of the bound term
    ratios = [int(r['boundary']) / int(r['trueBounds']) for r in srt if int(r['N']) >= 1000]
    chk('boundaryHeapSize is about twice the sum of the true bound sizes for N >= 1000 (the lines 178/766 double count)', all(1.99 <= x <= 2.0001 for x in ratios), f'min {min(ratios):.4f} max {max(ratios):.4f}')
    deep = [(int(r['unshared']) - int(r['deep']), int(r['trueBounds'])) for r in srt if 'deep' in r and int(r['N']) >= 1000]
    chk('unshared minus Jamm deep size equals the true bound sizes (within 0.1 %) for N >= 1000', all(abs(a - b) <= 0.001 * b + 256 for a, b in deep), f'{len(deep)} runs; max |a-b| = {max(abs(a - b) for a, b in deep)} B')
    # 5. the f dependence: recompute the pair check with BOTH the frozen definition and the f_eff variant
    by = collections.defaultdict(dict)
    for r in srt:
        if r['kind'] == 'sorted' and r['rep'] == '1': by[(r['s'], int(r['N']))][float(r['f'])] = int(r['unshared'])
    def pairs(feff):
        bad = []
        for (s, n), v in by.items():
            fs = sorted(v)
            for i in range(len(fs)):
                for j in range(i + 1, len(fs)):
                    a, b = fs[i], fs[j]
                    fm = max((x if (not feff or x >= 1.2) else 1.5) for x in (a, b))
                    if abs(v[a] - v[b]) > 28 * (math.ceil((fm - 1) * n) + 1): bad.append((s, n, a, b))
        return bad
    b1, b2 = pairs(False), pairs(True)
    print(f'     frozen R3 pair check violations: {len(b1)} {b1[:4]}; with f_eff: {len(b2)}')
    chk('every pair violating the frozen R3 pair bound contains a fallback factor (f <= 1.0) and none violates it with f_eff', all(min(a, b) <= 1.0 for (_, _, a, b) in b1) and not b2, f'{len(b1)} frozen violations')
    # 6. linear in N
    lin = collections.defaultdict(dict)
    for r in srt:
        if r['kind'] == 'sorted' and r['rep'] == '1': lin[(r['f'], r['s'])][int(r['N'])] = int(r['unshared'])
    rr = [v[max(v)] / v[1000] for v in lin.values() if 1000 in v and max(v) > 1000]
    hi = max(max(v) for v in lin.values()); lo = 1000
    chk(f'unshared(N={hi}) / unshared(N=1000) within [0.5, 1.5] x {hi // lo} in every (f, s) cell', all(0.5 * hi / lo <= x <= 1.5 * hi / lo for x in rr), f'min {min(rr):.1f} max {max(rr):.1f} over {len(rr)} cells')
    # 7. per-case
    if case in ('A', 'N'):
        cp = [r for r in rows if r['kind'] == 'sorted-copy' or r['kind'] == 'random-copy']
        if cp:
            chk('copy(): every array has length == size', all(set(r['lens'].split('/')) == {r['size']} for r in cp), f'{len(cp)} copies')
    ctrl = [r for r in srt if r['s'] == '1024' and int(r['N']) <= 1000]
    chk('control: initial capacity 1024 with N <= 1000 never grows, at every f (no event, all arrays 1024)', ctrl and all(r['events'] == '0' and set(r['lens'].split('/')) == {'1024'} for r in ctrl), f'{len(ctrl)} runs')
    for r in rows:
        if r['kind'] == 'addAll':
            pass
    aa = [r for r in rows if r['kind'] == 'addAll']
    if aa:
        chk('addAll into an empty list: all four array lengths == max(initial capacity, 1000) for every f', all(set(r['dstLens'].split('/')) == {str(max(int(r['s']), 1000))} for r in aa), f'{len(aa)} runs; capacities {sorted(set(r["dstLens"].split("/")[0] for r in aa))}')
    po = [r for r in rows if r['kind'] == 'plusone']
    if po: chk('N+1-th add accepted in every run', all(r['accepted'] == 'true' and int(r['after']) == int(r['N']) + 1 for r in po), f'{len(po)} runs')
    ca = [r for r in rows if r['kind'] == 'copyadd']
    if ca:
        bad = 0
        for r in ca:
            f = float(r['f'])
            for t in r['triples'].split(','):
                if t:
                    sb, cb, cA = map(int, t.split(':'))
                    if not (cb == sb and cA == grow_once(sb, f)): bad += 1
        chk('copy()+add loop: capacity == size after copy(), == grow expression after the add, in all 1000 iterations of every run', bad == 0, f'{len(ca)} runs, {bad} iterations differ')
    r100 = [r for r in srt if r['f'] == '100.0' and r['s'] == '1' and r['N'] == '100000' and r['rep'] == '1']
    if r100: chk('f = 100.0 from capacity 1: capacities 100, 10000, 1000000', [c for _, c in [tuple(map(int, p.split(':'))) for p in r100[0]['series'].split(',') if p]] == [100, 10000, 1000000])
    ctl = [r for r in rows if r['kind'] == 'control']
    if ctl and case == 'G':
        chk('LinkedHashMap control stays at 1000 entries while the list grows 1000 -> 10000 -> 100000', [int(r['boundedMapSize']) for r in ctl] == [1000] * 3 and [int(r['listSize']) for r in ctl] == [1000, 10000, 100000])
    rid = [r for r in rows if r['kind'] == 'repeat-identical']
    if rid: chk('the probe\'s own repeat check (3 repeats) says identical', rid[0]['value'] == 'true')
    grid = {'A': 6 * 3 * 3 * 3 * 2, 'G': 4 * 3 * 3, 'N': 7 * 2 * 4 * 2}[case]
    chk('number of sorted/random runs equals the grid of the case (B2b/B2c)', len(srt) == grid, f'{len(srt)} vs {grid}')

else:
    D = sys.argv[2]
    recs = [json.loads(l) for l in open(D + '/cells.jsonl')]
    case = recs[0]['case']
    # raw histogram parser over the jcmd output
    def histo(path):
        out = {}
        for l in open(path, errors='replace'):
            p = l.split()
            if len(p) >= 4 and p[0].endswith(':'):
                out[p[3]] = (int(p[1]), int(p[2]))
            elif p and p[0] == 'Total':
                out['TOTAL'] = (int(p[1]), int(p[2]))
        return out
    cells = collections.OrderedDict()
    for r in recs:
        if r['kind'] in ('base', 'cp', 'end'):
            cells.setdefault(r['cell'], {'cps': []})
            if r['kind'] == 'cp': cells[r['cell']]['cps'].append(r)
            elif r['kind'] == 'base': cells[r['cell']]['base'] = r
            else: cells[r['cell']]['end'] = r
    # 1. recorded counters agree with the 2-s series (the series' values bracket each checkpoint's counter)
    bad = 0
    for lab, c in cells.items():
        ser = [l.split(',') for l in open(f'{D}/{lab}/series.csv') if l.count(',') == 2 and l.split(',')[1].isdigit()]
        vals = [int(x[1]) for x in ser]
        for cp in c['cps']:
            if int(cp['metrics']['counter']) not in vals and not (min(vals) <= int(cp['metrics']['counter']) <= max(vals)): bad += 1
    chk('every checkpoint counter lies within the range of the 2-second counter series of its cell', bad == 0, f'{sum(len(c["cps"]) for c in cells.values())} checkpoints, {bad} outside')
    # 2. histogram files re-parsed raw: live tombstones = BufferClusteringBound/2 and allocated slots from ClusteringBound[] bytes
    out = []
    bad = 0
    for lab, c in cells.items():
        if c['base']['load'] == 'ins': continue
        f = float(c['base']['factor_read'])
        b = histo(f'{D}/{lab}/histo-base.txt')
        for cp in c['cps']:
            h = histo(f'{D}/{lab}/histo-cp{cp["k"]}.txt')
            live = (h['org.apache.cassandra.db.BufferClusteringBound'][0] - b.get('org.apache.cassandra.db.BufferClusteringBound', (0, 0))[0]) / 2
            cb = h['[Lorg.apache.cassandra.db.ClusteringBound;']; cb0 = b.get('[Lorg.apache.cassandra.db.ClusteringBound;', (0, 0))
            slots = ((cb[1] - cb0[1]) - 16 * (cb[0] - cb0[0])) / 8
            if c['base']['control']:
                print(f'     control {lab} cp{cp["k"]}: live tombstones {live:.0f} of {cp["tombstones"]} written (the rest was flushed, by design)')
            elif abs(live - cp['tombstones']) > 0.01 * cp['tombstones'] + 5: bad += 1
            # slack per partition after the last merge is ceil(f*(n-1)) - n  -> slots/live is between 1 and f_eff (+ rounding)
            if cp['k'] == len(c['cps']) and not c['base']['control']:
                out.append((lab, f, round(slots / live, 3)))
    chk('raw histograms: live tombstones (BufferClusteringBound/2) == tombstones written at every checkpoint of every flush-free range-delete cell (controls excluded: they flush by design)', bad == 0, f'{bad} off by more than 1 %')
    chk('raw histograms: allocated slots / live tombstones at the last checkpoint is within [1, f] of the cell factor (one growth per merge)', all(1.0 <= r <= f + 0.02 for _, f, r in out), str(out[:6]))
    # 3. the writes in session.log: count acknowledged vs the sum of checkpoint loads
    ses = open(D + '/session.log', errors='replace').read()
    oks = [int(x) for x in re.findall(r"checkpoint \d+: per-partition \d+->\d+: \{'ok': (\d+), 'expected': (\d+), 'errors': (\d+)", ses) for x in [x]] if False else None
    m = re.findall(r"checkpoint \d+: per-partition \d+->\d+: \{'ok': (\d+), 'expected': (\d+), 'errors': (\d+)", ses)
    chk('session.log: every checkpoint load acknowledged all its writes with 0 errors', m and all(a == b and e == '0' for a, b, e in m), f'{len(m)} loads, {sum(int(a) for a, _, _ in m)} writes')
    # 4. system.log segments: no ERROR/OOM; every flush of ks.t / ks.t2 with its Reason and time (UTC) against the cell's load window
    import datetime
    def utc_ms(ts): return int(datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    for seg in sorted(glob.glob(D + '/system-*.log')):
        txt = open(seg, errors='replace').read()
        life = os.path.basename(seg)[7:-4]
        errs = [l for l in txt.splitlines() if l.startswith('ERROR') or 'java.lang.OutOfMemoryError' in l]
        chk(f'system.log {life}: no ERROR / OutOfMemoryError line', not errs, f'{len(errs)} lines')
        fl = [(utc_ms(m.group(1)), m.group(2), m.group(3)) for m in re.finditer(r'(\d{4}-\d\d-\d\dT[\d:]+,\d+) ColumnFamilyStore.java:\d+ - Enqueuing flush of ks\.t2?, Reason: (\w+), Usage: ([^\n]*?) on-heap', txt)]
        reasons = collections.Counter(r for _, r, _ in fl)
        lc = [c for c in cells.values() if c['base']['life'] == life]
        in_load = 0
        for c in lc:
            t0 = c['cps'][0]['t_start_ms']; t1 = c['cps'][-1]['t_end_ms']
            in_load += sum(1 for t, r, _ in fl if t0 <= t <= t1 and r != 'USER_FORCED')
        ctl = any(c['base']['control'] for c in lc)
        if ctl:
            chk(f'system.log {life} (control): memtable-limit flushes of ks.t/t2 happened during the load', reasons.get('MEMTABLE_LIMIT', 0) >= 1 and in_load >= 1, f'reasons {dict(reasons)}; {in_load} non-user flushes inside the load windows')
        else:
            chk(f'system.log {life}: the only flushes of ks.t/t2 are USER_FORCED (my nodetool flush calls), none from the memtable limit, none inside a load window', set(reasons) <= {'USER_FORCED'} and in_load == 0, f'reasons {dict(reasons)}; usage at the forced flushes: {[u for _, _, u in fl][:4]}')
    # 5. trace lines: ratio newLength/cap per cell
    for lab, c in cells.items():
        p = f'{D}/{lab}/growth-trace.txt'
        rs = [int(m.group(2)) / int(m.group(1)) for m in (re.match(r'grow n=\d+ index=\d+ cap=(\d+) newLength=(\d+)', l) for l in open(p)) if m and int(m.group(1)) >= 100]
        if rs:
            f = float(c['base']['factor_read'])
            chk(f'trace {lab}: sampled newLength/cap (cap >= 100) is within [f, f + 1/100] of the cell factor {f}', all(f - 1e-9 <= x <= f + 0.01 + 1e-9 for x in rs), f'{len(rs)} lines, min {min(rs):.4f} max {max(rs):.4f}')
    # 6. flush counts re-derived: switch count at start/end of each cell from cells.jsonl vs 'end' record
    for lab, c in cells.items():
        s0, s1 = int(c['base']['metrics']['switch']), int(c['end']['metrics']['switch'])
        print(f'     {lab}: MemtableSwitchCount start {s0}, end(after final flush) {s1}; last checkpoint {c["cps"][-1]["metrics"]["switch"]}')
    print('process check (manual): ps -eo cmd | grep [C]assandraDaemon after the run')
