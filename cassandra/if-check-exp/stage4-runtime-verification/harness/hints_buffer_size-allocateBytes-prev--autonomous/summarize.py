#!/usr/bin/env python3
"""Readings tables for hints_buffer_size-allocateBytes-prev--autonomous (B2f/B2g and B3f/B3g as amended 2026-10-26).

usage: summarize.py unit <unit log dir>        (reads hbcap.txt, ant.log)
       summarize.py cluster <cluster log dir>  (reads summary.txt, arm-*/node1.out, arm-*/samples.tsv, arm-*/stress-*.log)
Prints a readings table and the row each tier matches. The independent check is run1/selfcheck.py, not this file.
"""
import os
import re
import statistics
import sys

MiB = 1 << 20


def kv(line):
    return dict(re.findall(r'(\w+)=(\S+)', line))


def unit(d):
    lines = [l.strip() for l in open(os.path.join(d, 'hbcap.txt')) if l.startswith('HBCAP')]
    ant = open(os.path.join(d, 'ant.log')).read()
    setup = [kv(l) for l in lines if l.startswith('HBCAP setup')]
    c1 = [kv(l) for l in lines if l.startswith('HBCAP case=1')]
    c2 = {int(kv(l)['B']): kv(l) for l in lines if l.startswith('HBCAP case=2')}
    c3 = [kv(l) for l in lines if l.startswith('HBCAP case=3 B=')]
    c3e = [kv(l) for l in lines if l.startswith('HBCAP case=3 end')]
    fo = [kv(l) for l in lines if l.startswith('HBCAP formula')]
    print('UNIT tests: ' + (re.search(r'Tests run: \d+, Failures: \d+, Errors: \d+', ant).group(0) if 'Tests run' in ant else 'none'))
    print('UNIT setup: ' + str(setup))
    fails, notconf, refuted_cap, refuted_mem = [], [], [], []
    n_by_b = {}
    print('| B | e | n | floor(B/e) | sum | B-e<sum<=B | remaining | nextNull | alloc1Null | leftover | found/foundBytes | dmem1-dmem0 | cnt1-cnt0 | dmem2-dmem1 | dmem3-dmem0 | case 2 |')
    for r in c1:
        B, e, emin, emax = (int(r[k]) for k in ('B', 'e', 'emin', 'emax'))
        n, s = int(r['n']), int(r['sum'])
        d10, c10 = int(r['dmem1']) - int(r['dmem0']), int(r['cnt1']) - int(r['cnt0'])
        d21, c21 = int(r['dmem2']) - int(r['dmem1']), int(r['cnt2']) - int(r['cnt1'])
        d30, c30 = int(r['dmem3']) - int(r['dmem0']), int(r['cnt3']) - int(r['cnt0'])
        lo = int(r['leftover'])
        n_by_b[B] = n
        t2 = c2.get(B, {}).get('threw', 'missing')
        print(f"| {B} | {e} | {n} | {B // e} | {s} | {B - e < s <= B} | {r['remaining']} | {r['nextNull']} | {r['alloc1Null']} | {lo} | {r['found']}/{r['foundBytes']} | {d10} | {c10} | {d21} | {d30} | {t2} |")
        if emin != emax:
            notconf.append(f'B={B} e varies')
        if s > B or int(r['found']) > n or int(r['foundBytes']) > s:
            refuted_cap.append(f'B={B} sum/found above B')
        if lo >= 13 and r['alloc1Null'] != 'true':
            refuted_cap.append(f'B={B} allocate(1) accepted on a closed slab')
        if (c10 == 1 and d10 != B) or (d21 > 0 and c21 == 0):
            refuted_mem.append(f'B={B} dmem delta {d10}/{d21}')
        if c10 != 1 or c21 != 0 or d30 != 0 or c30 != 0:
            notconf.append(f'B={B} other allocator (cnt {c10},{c21},{c30}; dmem3-dmem0 {d30})')
        exp = [n == B // e, B - e < s <= B, r['nextNull'] == 'true', r['remaining'] == '0', int(r['found']) == n,
               int(r['foundBytes']) == s, d10 == B, c10 == 1, d21 == 0, c21 == 0, d30 == 0, c30 == 0, t2 == 'java.lang.IllegalArgumentException']
        if lo >= 13:
            exp.append(r['alloc1Null'] == 'true')
        if not all(exp):
            fails.append(f'B={B} prediction cells {exp}')
        if t2 != 'java.lang.IllegalArgumentException':
            notconf.append(f'B={B} case 2 did not throw')
    if 33554432 in n_by_b and 67108864 in n_by_b:
        ok = n_by_b[67108864] in (2 * n_by_b[33554432], 2 * n_by_b[33554432] + 1)
        print(f'UNIT n(64MiB)={n_by_b[67108864]} n(32MiB)={n_by_b[33554432]} doubling={ok}')
        if not ok:
            fails.append('doubling')
        if n_by_b[67108864] == n_by_b[33554432]:
            refuted_cap.append('n flat across B')
    for r in c3:
        B = int(r['B'])
        print('UNIT case3 ' + ' '.join(f'{k}={v}' for k, v in r.items()) + f" | dmem1-dmem0={int(r['dmem1']) - int(r['dmem0'])} (3B={3 * B}) cnt1-cnt0={int(r['cnt1']) - int(r['cnt0'])}")
        ok3 = (r['allocatedBuffers'] == '3' and r['max'] == '3' and r['held'] == '2' and r['writerState'] == 'WAITING' and r['inTake'] == 'true'
               and int(r['hintsWritten']) < int(r['hintsToWrite']) and int(r['dmem1']) - int(r['dmem0']) == 3 * B and int(r['cnt1']) - int(r['cnt0']) == 3)
        print(f'UNIT case3 prediction holds={ok3}' + ('  (allocatedBuffers > 3: not this claim)' if int(r['allocatedBuffers']) > 3 else ''))
    for r in c3e:
        print('UNIT case3-end ' + ' '.join(f'{k}={v}' for k, v in r.items()))
    print('UNIT formula ' + ' '.join(f"M={r['M']}->B={r['B']}" for r in fo))
    expected_sizes = {1048576, 33554432, 67108864}
    if not c1 or not setup or setup[0].get('maxDirectMemorySize') != '1g' or set(n_by_b) != expected_sizes:
        row = 'Invalid'
    elif refuted_cap:
        row = 'Refuted (cap) ' + '; '.join(refuted_cap)
    elif refuted_mem:
        row = 'Refuted (real resource) ' + '; '.join(refuted_mem)
    elif notconf or fails:
        row = 'Not confirmed ' + '; '.join(notconf + fails)
    else:
        row = 'Confirmed (row 1)'
    print('UNIT-ROW ' + row)


def cluster(d):
    summ = open(os.path.join(d, 'summary.txt')).read().splitlines()
    marks, stressr, arms = {}, {}, []
    for l in summ:
        m = re.match(r'MARK (\w+) ([\w-]+) ms=(\d+) off=(\d+)', l)
        if m:
            marks[(m.group(1), m.group(2))] = (int(m.group(3)), int(m.group(4)))
        m = re.match(r'STRESS (\w+) ([UD]) \| rc=(\d+) \| (.*)', l)
        if m:
            t = m.group(4)
            part = re.search(r'Total partitions\s*:\s*([\d,]+)', t)
            err = re.search(r'Total errors\s*:\s*([\d,]+)', t)
            stressr[(m.group(1), m.group(2))] = (int(m.group(3)), int(part.group(1).replace(',', '')) if part else -1,
                                                  int(err.group(1).replace(',', '')) if err else -1)
        m = re.match(r'ARM (\w+) B_arm=(\d+)', l)
        if m:
            arms.append((m.group(1), int(m.group(2))))
    nw = int(re.search(r'NW=(\d+)', summ[0]).group(1))
    steps = {}
    rows = {}
    hd = {}
    for a, B in arms:
        ad = os.path.join(d, 'arm-' + a)
        raw = open(os.path.join(ad, 'node1.out'), 'rb').read()
        lines, pos = [], 0
        for bl in raw.split(b'\n'):
            s = bl.decode('utf-8', 'replace')
            if s.startswith('HBCAP'):
                lines.append((pos, s))
            pos += len(bl) + 1
        uS, dS, tE = marks[(a, 'U-start')], marks[(a, 'D-start')], marks[(a, 'tail-end')]
        creates = [int(kv(s)['slabSize']) for p, s in lines if s.startswith('HBCAP create')]
        fulls = [(p, kv(s)) for p, s in lines if s.startswith('HBCAP full')]
        fullD = [f for f in fulls if f[0] >= dS[1]]
        caps = sorted({int(f[1]['cap']) for f in fulls})
        alloc = [(p, int(s.split('=')[1])) for p, s in lines if s.startswith('HBCAP allocatedBuffers=')]
        k0 = max([v for p, v in alloc if p < dS[1]], default=0)
        k1 = max([v for p, v in alloc if p < tE[1]], default=0)
        createsBeforeU = sum(1 for p, s in lines if s.startswith('HBCAP create') and p < uS[1])
        dm = [(p, s) for p, s in lines if s.startswith('HBCAP dmem')]
        pairs, i = [], 0
        while i + 1 < len(dm):
            if dm[i][1].startswith('HBCAP dmem before') and dm[i + 1][1].startswith('HBCAP dmem after'):
                b, af = kv(dm[i][1]), kv(dm[i + 1][1])
                pairs.append((int(af['cap']), int(af['used']) - int(b['used']), int(af['count']) - int(b['count'])))
                i += 2
            else:
                i += 1
        afterCaps = sorted({p[0] for p in pairs})
        smp = []
        for l in open(os.path.join(ad, 'samples.tsv')):
            f = l.split()
            if not f or f[0].startswith('#') or f[1] == 'ERR':
                continue
            smp.append(tuple(int(x) for x in f))
        def win(t0, t1):
            return [s for s in smp if t0 <= s[0] <= t1]
        def last_before(t):
            c = [s for s in smp if s[0] <= t]
            return c[-1] if c else None
        s0w = win(dS[0] - 15000, dS[0]); s1w = win(tE[0] - 15000, tE[0])
        S0 = statistics.median(s[1] for s in s0w) if s0w else None
        S1 = statistics.median(s[1] for s in s1w) if s1w else None
        uE, dE = marks[(a, 'U-end')], marks[(a, 'D-end')]
        bu, bd = last_before(uS[0]), last_before(dS[0])
        dU = max(s[1] for s in win(uS[0], uE[0])) - bu[1] if bu else None
        dD = max(s[1] for s in win(dS[0], tE[0])) - bd[1] if bd else None
        th0, th1 = bd[4] if bd else None, last_before(tE[0])[4]
        hdir = last_before(tE[0])[5]
        hd[a] = hdir
        settled = (S1 - S0) if S0 is not None and S1 is not None else None
        exp5 = (k1 - k0) * B
        good_pairs = [p for p in pairs if p[2] == 1]
        steps[a] = sorted({p[1] for p in good_pairs})
        su, sd = stressr.get((a, 'U'), (-1, -1, -1)), stressr.get((a, 'D'), (-1, -1, -1))
        P1 = bool(creates) and all(c == B for c in creates) and bool(afterCaps) and all(c == B for c in afterCaps)
        P2 = bool(fullD) and all(c == B for c in caps)
        P3 = 2 <= k1 <= 3
        P4 = bool(good_pairs) and all(p[1] == B for p in good_pairs)
        P5 = settled is not None and abs(settled - exp5) <= 8 * MiB
        P7a = th0 is not None and th1 - th0 >= 0.95 * nw
        P7b = hdir >= B
        P8 = su[0] == 0 and sd[0] == 0 and su[1] == nw and sd[1] == nw and su[2] == 0 and sd[2] == 0
        agent_err = sum(1 for l in raw.decode('utf-8', 'replace').splitlines() if re.search(r'Rule\.execute called for|TypeException', l))
        inval = createsBeforeU == 0 or agent_err > 0 or len(s0w) < 10 or len(s1w) < 10 or not (su[2] == 0 and sd[2] == 0)
        print(f'ARM {a} B_arm={B}: creates={creates} createsBeforeU={createsBeforeU} dmemAfterCaps={afterCaps} full_lines={len(fulls)} full_in_D={len(fullD)} caps={caps}')
        print(f'ARM {a}: allocatedBuffers={[v for p, v in alloc]} k0={k0} k1={k1} dmem_pairs(cap,step,countstep)={pairs}')
        print(f'ARM {a}: S0={S0} (n={len(s0w)}) S1={S1} (n={len(s1w)}) S1-S0={settled} expected (k1-k0)*B={exp5} diff={None if settled is None else settled - exp5} | dU={dU} dD={dD} dD-dU={None if dU is None or dD is None else dD - dU}')
        print(f'ARM {a}: TotalHints D: {th0} -> {th1} (delta {None if th0 is None else th1 - th0}); hints_dir_bytes at tail end={hdir} files={last_before(tE[0])[6]} | stress U={su} D={sd} (rc, partitions, errors) | agent_errors={agent_err}')
        print(f'ARM {a}: P1={P1} P2={P2} P3={P3} P4={P4} P5={P5} P7a={P7a} P7b={P7b} P8={P8} invalid={inval}')
        if inval:
            rows[a] = 'Invalid'
        elif not all(c == B for c in creates):
            rows[a] = 'Refuted (row 2)'
        elif not all(c == B for c in caps) or any(p[1] != B for p in good_pairs) or not all(c == B for c in afterCaps):
            rows[a] = 'Refuted (row 3)'
        elif not fullD:
            rows[a] = 'Not confirmed (row 5)'
        elif not (P7a and P7b):
            rows[a] = 'Not confirmed (row 6)'
        elif k1 < 2:
            rows[a] = 'Not confirmed (row 7)'
        elif not P5:
            rows[a] = 'Not confirmed (row 4)'
        elif P1 and P2 and P3 and P4 and P5 and P8:
            rows[a] = 'Confirmed (row 1)'
        else:
            rows[a] = 'Not confirmed (other)'
        if k1 > 3:
            rows[a] += ' + k1>3 (not this claim)'
        print(f'ARM {a} ROW {rows[a]}')
    if len(hd) == 3:
        mean = sum(hd.values()) / 3
        within = all(abs(v - mean) <= 0.10 * mean for v in hd.values())
        print(f'P7 across arms: hints_dir_bytes={hd} mean={mean:.0f} within10%={within}')
        if not within:
            for a in rows:
                if rows[a].startswith('Confirmed'):
                    rows[a] = 'Not confirmed (row 6, P7 spread)'
    if 'i' in steps and steps['i']:
        print('P6 per-slab steps: ' + ' '.join(f'{a}={steps[a]}' for a in steps) + ' ratios ' +
              ' '.join(f"{a}/i={[s / steps['i'][0] for s in steps[a]]}" for a in steps))
    allr = list(rows.values())
    if allr and all(r.startswith('Confirmed') for r in allr) and len(allr) == 3:
        tier = 'Confirmed (row 1)'
    elif any(r.startswith('Refuted') for r in allr):
        tier = 'Refuted'
    elif any(r.startswith('Invalid') for r in allr):
        tier = 'Invalid'
    else:
        tier = 'Not confirmed'
    print('CLUSTER-ROW ' + tier + ' ' + str(rows))


if __name__ == '__main__':
    {'unit': unit, 'cluster': cluster}[sys.argv[1]](sys.argv[2])
