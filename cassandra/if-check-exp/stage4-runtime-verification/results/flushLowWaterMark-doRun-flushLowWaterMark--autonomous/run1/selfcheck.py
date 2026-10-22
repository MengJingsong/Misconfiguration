#!/usr/bin/env python3
"""Self-check for flushLowWaterMark-doRun-flushLowWaterMark--autonomous, run 1 (results section 5).
Re-parses the raw files independently of the harness's own summaries and applies the frozen rules
(unit: B2f + A3, rows in A4 order; cluster: B3f + A9, rows in A10 order). Prints one line per check.
usage: python3 selfcheck.py unit <unit.csv>
       python3 selfcheck.py cluster <dir with V*-r*/ lifetime folders: jmx.csv, vt-out.csv, flw.trace, times.json, A-system.log>
"""
import csv, json, os, re, statistics, sys

MIB = 1 << 20


def unit(path):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        for k in ('H', 'L', 'S', 'N', 'U', 'P', 'nR', 'flips', 'guardMiss', 'inferErr', 'failed', 'enqueued', 'handled',
                  'templateH', 'templateL', 'establishedH', 'establishedL', 'peakPre'):
            r[k] = int(r[k])
        for k in ('maxR', 'medR', 'minR'):
            r[k] = int(r[k]) if r[k] != '' else None
        r['stalled'] = r['writableAtStable'] == 'false'
    print(f'rows {len(rows)}: ' + ', '.join(f'{s}={sum(1 for r in rows if r["set"] == s)}' for s in ('S0', 'L', 'P')))
    # row 1: invalid
    rb = [r for r in rows if (r['templateH'], r['templateL']) != (r['H'], r['L']) or (r['establishedH'], r['establishedL']) != (r['H'], r['L'])]
    inc = [r for r in rows if r['failed'] or r['handled'] != r['enqueued']]
    print(f'A4.1 read-back mismatches {len(rb)}; failed frames or handled != enqueued {len(inc)}')
    # row 2
    ns = [r for r in rows if not r['stalled']]
    print(f'A4.2 never stalled {len(ns)}; P > S in all {all(r["P"] > r["S"] for r in rows)}')
    Ls = [r for r in rows if r['set'] == 'L']
    Ps = [r for r in rows if r['set'] == 'P']
    S0 = [r for r in rows if r['set'] == 'S0']
    belowH = [r for r in Ls + Ps if r['S'] < r['H']]
    print(f'A4.2 L/P runs with S < H: {len(belowH)}')
    pin = {H: [r['S'] for r in Ps if r['H'] == H] for H in (65536, 1048576, 8388608)}
    p_ok = all(H <= s < H + 65536 for H, v in pin.items() for s in v)
    ratio = min(pin[8388608]) / max(pin[65536])
    print(f'A4.2/B2f P-set S by H: {pin}; all in [H, H+65536): {p_ok}; S(8 MiB)/S(64 KiB) worst-case ratio {ratio:.2f} (>= 64: {ratio >= 64})')
    # row 3: trend on per-L medians
    Lv = (1024, 32768, 524288, 1040384)
    for k, thr in (('S', 65536), ('N', 65536), ('U', 262144)):
        meds = [statistics.median([r[k] for r in Ls if r['L'] == L]) for L in Lv]
        allv = [r[k] for r in Ls]
        spread = max(allv) - min(allv)
        mspread = max(meds) - min(meds)
        mono = all(a <= b for a, b in zip(meds, meds[1:])) or all(a >= b for a, b in zip(meds, meds[1:]))
        print(f'A4.3 {k}: per-L medians {meds}; monotone {mono}; median spread {mspread}; spread over 12 runs {spread} '
              f'(threshold {thr}); follows L: {mono and mspread >= thr}')
    # row 4: mechanism
    rgt = [r for r in rows if r['maxR'] is not None and r['maxR'] > r['L']]
    gm = sum(r['guardMiss'] for r in rows); ie = sum(r['inferErr'] for r in rows)
    over = [r for r in Ls + Ps if r['S'] >= r['H'] + 65536]
    print(f'A4.4 runs with max R > L: {len(rgt)}; guardMiss total {gm}; inferErr total {ie}; L/P runs with S >= H+65536: {len(over)}')
    noR = [r for r in rows if r['nR'] == 0]
    print(f'      runs with no R recorded: {len(noR)}; flips per run min/max {min(r["flips"] for r in rows)}/{max(r["flips"] for r in rows)}')
    for L in Lv:
        rr = [r for r in Ls if r['L'] == L]
        print(f'      L={L}: R max per run {[r["maxR"] for r in rr]}, median per run {[r["medR"] for r in rr]}, min per run {[r["minR"] for r in rr]}')
    medR_hi = statistics.median([r['medR'] for r in Ls if r['L'] == 1040384])
    print(f'B2f manipulation: median R for L=1040384 (median of per-run medians) {medR_hi} > 524288: {medR_hi > 524288}; '
          f'max R for L=1024 {max(r["maxR"] for r in Ls if r["L"] == 1024)} <= 1024')
    # row 5/6: U and N bounds
    print(f'A4.5 U spread over L-set {max(r["U"] for r in Ls) - min(r["U"] for r in Ls)} (>= 262144 is row 5)')
    nbad = [r for r in Ps if not (r['S'] <= r['N'] < r['S'] + 65536)]
    ubad = [r for r in Ps if not (r['S'] <= r['U'] <= r['S'] + 262144)]
    print(f'A3 P-set: runs with N outside [S, S+65536): {len(nbad)} of {len(Ps)} (N values {sorted({r["N"] for r in Ps})}); '
          f'runs with U outside [S, S+262144]: {len(ubad)} of {len(Ps)}')
    print(f'B2f L-set N spread {max(r["N"] for r in Ls) - min(r["N"] for r in Ls)} (< 65536); U spread < 262144: '
          f'{max(r["U"] for r in Ls) - min(r["U"] for r in Ls) < 262144}; L-set S each in [H, H+65536): '
          f'{all(1048576 <= r["S"] < 1114112 for r in Ls)}')
    for r in S0:
        print(f'S0 baseline rep {r["rep"]}: S {r["S"]} in [65536,131072) {65536 <= r["S"] < 131072}; N {r["N"]} in [S,S+4096] '
              f'{r["S"] <= r["N"] <= r["S"] + 4096}; U {r["U"]} in [S,S+262144] {r["S"] <= r["U"] <= r["S"] + 262144}; P>S {r["P"] > r["S"]}; '
              f'R<=32768 {r["maxR"] is None or r["maxR"] <= 32768}')
    print('N / 96 per run (Netty per-entry overhead; NoSizeEstimator counts 0 bytes per frame): '
          + str(sorted({(r['H'], r['N'], r['N'] / 96) for r in rows})))


def cluster(d):
    HL = {'V0': (65536, 32768), 'V1': (1 << 26, 1 << 10), 'V2': (1 << 26, 1 << 25), 'V3': (1 << 26, (1 << 26) - (1 << 20)),
          'V4': (1 << 22, 1 << 21)}
    D = {}
    for v in HL:
        for rep in (1, 2):
            p = f'{d}/{v}-r{rep}'
            if not os.path.isdir(p):
                print(f'{v}-r{rep}: missing'); continue
            t = json.load(open(f'{p}/times.json'))
            p0, pc = t['pause'], t['cont']
            used = []
            hdr = None
            for l in open(f'{p}/jmx.csv'):
                f = l.strip().split(',')
                if hdr is None:
                    hdr = f; continue
                if len(f) != len(hdr) or not f[0].isdigit():
                    continue
                rec = dict(zip(hdr, f))
                try:
                    used.append((int(rec['ms']), int(rec['used']), int(rec['smallPending'])))
                except ValueError:
                    pass
            pre = [u for ms, u, _ in used if p0 - 11000 <= ms <= p0 - 1000]
            pla = [u for ms, u, _ in used if p0 + 10000 <= ms <= p0 + 22000]
            Dv = statistics.median(pla) - statistics.median(pre)
            spmax = max(s for ms, _, s in used if p0 <= ms <= pc)
            vt = [l.strip().split(',') for l in open(f'{p}/vt-out.csv') if l.startswith('1') and ',127.0.0.2,' in l]
            act = [int(x[13]) for x in vt if p0 <= int(x[0]) <= pc]
            vpend = [int(x[6]) for x in vt if p0 <= int(x[0]) <= pc]
            st, rs = [], []
            for l in open(f'{p}/flw.trace'):
                f = l.split()
                if f and f[0] == 'STALL':
                    st.append((int(f[1]), f[2], f[3], int(f[5]), int(f[6]), int(f[7])))
                elif f and f[0] == 'RESUME':
                    rs.append((int(f[1]), f[2], f[3], int(f[5]), int(f[6])))
            H, L = HL[v]
            hl = {(s[4], s[5]) for s in st}
            oor = [s for s in st if not (H <= s[3] < H + 65536)]
            rgt = [r for r in rs if r[3] > L]
            sf = [s for s in st if p0 <= s[0] <= pc and s[1] == 'SMALL_MESSAGES' and '127.0.0.2' in s[2]]
            log = open(f'{p}/A-system.log').read() if os.path.exists(f'{p}/A-system.log') else ''
            down = len(re.findall(r'127\.0\.0\.2:7000 is now DOWN', log)); intr = log.count('Interrupted outbound connections to /127.0.0.2')
            D[(v, rep)] = Dv
            print(f'{v}-r{rep}: pre n={len(pre)} plateau n={len(pla)} D={Dv} ({Dv/MIB:.3f} MiB); smallPending max in freeze {spmax} '
                  f'({spmax/MIB:.1f} MiB); vt pending max {max(vpend) if vpend else None}; active_connections min {min(act) if act else None}; '
                  f'STALL {len(st)} (H,L) {sorted(hl)} expected {(H, L)}; out of [H,H+64K) {len(oor)}; RESUME {len(rs)} >L {len(rgt)}; '
                  f'small-link stalls in freeze {len(sf)} max {max((s[3] for s in sf), default=None)}; DOWN {down} interrupted {intr}')
    m = {v: statistics.mean([D[(v, r)] for r in (1, 2) if (v, r) in D]) for v in HL if any((v, r) in D for r in (1, 2))}
    print('means (MiB): ' + ', '.join(f'{v} {x/MIB:.3f}' for v, x in m.items()))
    if all(v in m for v in ('V1', 'V2', 'V3')):
        a = [m['V1'], m['V2'], m['V3']]
        pair = max(abs(x - y) for x in a for y in a)
        mono = a[0] <= a[1] <= a[2] or a[0] >= a[1] >= a[2]
        print(f'V1-V3 pairwise max {pair/MIB:.3f} MiB (<= 4: {pair <= 4*MIB}); monotone {mono}; ordered by L {mono and pair > 4*MIB}')
        print('each V1-V3 lifetime in [64,70] MiB: ' + str({f'{v}-r{r}': 64*MIB <= D[(v, r)] <= 70*MIB for v in ('V1', 'V2', 'V3') for r in (1, 2) if (v, r) in D}))
    if 'V4' in m:
        print('each V4 lifetime in [4,8] MiB: ' + str({f'V4-r{r}': 4*MIB <= D[('V4', r)] <= 8*MIB for r in (1, 2) if ('V4', r) in D}))
        if 'V2' in m:
            print(f'D(V2)-D(V4) {(m["V2"]-m["V4"])/MIB:.3f} MiB (>= 56: {m["V2"]-m["V4"] >= 56*MIB})')
    if 'V0' in m:
        print(f'D(V0) {m["V0"]/MIB:.3f} MiB (< 1: {m["V0"] < MIB})')


if __name__ == '__main__':
    {'unit': unit, 'cluster': cluster}[sys.argv[1]](sys.argv[2])
