#!/usr/bin/env python3
"""Independent self-check of run 1 of maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous (results §5).
usage: selfcheck.py [<logs root, default ~/stage4-logs/mhp>]
Re-reads the RAW files, not the run scripts' summaries where a raw file exists:
  unit:    <root>/run1/unit-{orig,fixed}/ant.log and <root>/run1-rep2/unit-{orig,fixed}/ant.log — the test's own output
           fragments (SubstituteLogger lines) re-joined here with a different method than unit-run.sh (concatenate the
           messages, then one regex per line kind); the JUnit XML's counts; the javap field line of summary.txt.
  cluster: <root>/run1/cluster/<run>/samples.csv (200 ms JMX sampler), oldgen.csv, stress-main.out (results block,
           warm-up line, every "Too many in flight hints: N" message), n1-logs/{system,debug}.log, n1-yaml.diff; from
           summary.txt only the lines the run script logged from tools that leave no file of their own (the JMX get
           before/after, the hint-directory size, the field check).
Every check prints "ok" or "FAIL"; a total at the end. B2f/B2g and B3f/B3g are re-applied from these readings."""
import json, os, re, sys

ROOT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/stage4-logs/mhp')
TOT = {'ok': 0, 'FAIL': 0}
MAX = 2147483647


def chk(desc, cond):
    k = 'ok' if cond else 'FAIL'
    TOT[k] += 1
    print(f'{k:4s} {desc}')
    return cond


# ------------------------------------------------------------------ unit tier
def unit_lines(antlog):
    msgs = []
    started = False
    for l in open(antlog, errors='replace'):
        m = re.search(r'SubstituteLogger\.java:\d+ - (.*)$', l.rstrip('\n'))
        if not m:
            continue
        if m.group(1).startswith('INFO maxHeapMiB='):
            started = True
        if started:
            msgs.append(m.group(1))
    s = ''.join(msgs)        # the pieces of one printf are consecutive messages; join without separators
    info = re.search(r'INFO maxHeapMiB=\s*(\d+)\s+concurrentWriters=\s*(\d+)\s+defaultMaxHintsInProgress=\s*(\d+)\s+'
                     r'totalHintsInProgress0=\s*(\d+)\s+isSelf=\s*(\w+)\s+counterClass=\s*(\S+?)(?=RESULT|$)', s)
    res = [dict(L=int(a), queued=int(b), rejected=int(c), perDest=int(d), same=e == 'true', shouldHint=f == 'true',
                heapMiB=int(g), heapBytes=int(h))
           for a, b, c, d, e, f, g, h in re.findall(
               r'RESULT L=\s*(\d+)\s+queued=\s*(\d+)\s+rejected=\s*(\d+)\s+perDest=\s*(-?\d+)\s+same=\s*(\w+?)\s*'
               r'shouldHint=\s*(\w+?)\s*heapDeltaMiB=\s*(-?\d+)\s+heapDeltaBytes=\s*(-?\d+)', s)]
    drained = [(int(a), int(b)) for a, b in re.findall(r'DRAINED L=\s*(\d+)\s+remaining=\s*(\d+)', s)]
    return info, res, drained


def unit():
    print('== unit tier (B2f / B2g)')
    for rep in ('run1', 'run1-rep2'):
        for b in ('orig', 'fixed'):
            d = f'{ROOT}/{rep}/unit-{b}'
            info, res, dr = unit_lines(d + '/ant.log')
            tag = f'{rep} {b}'
            x = open([f'{d}/{f}' for f in os.listdir(d) if f.startswith('TEST-')][0]).read()
            m = re.search(r'errors="(\d+)" failures="(\d+)".*?tests="(\d+)"', x, re.S)
            chk(f'{tag}: JUnit XML tests=1 failures=0 errors=0 ({m.groups() if m else None})', m and m.groups() == ('0', '0', '1'))
            field = re.search(r'field: .*cache\.(\w+)<', open(d + '/summary.txt').read())
            want = 'CacheLoader' if b == 'orig' else 'LoadingCache'
            chk(f'{tag}: build field hintsInProgress is {want} ({field.group(1) if field else None})', field and field.group(1) == want)
            chk(f'{tag}: INFO line parsed (maxHeapMiB={info.group(1) if info else None}, concurrentWriters={info.group(2) if info else None}, '
                f'totalHintsInProgress0={info.group(4) if info else None}, isSelf={info.group(5) if info else None})',
                info is not None and info.group(4) == '0' and info.group(5) == 'false')
            chk(f'{tag}: four RESULT lines for L = 1, 128, 1000, MAX', [r['L'] for r in res] == [1, 128, 1000, MAX])
            chk(f'{tag}: four DRAINED lines, remaining = 0 ({dr})', len(dr) == 4 and all(rem == 0 for _, rem in dr))
            for r in res:
                L = r['L']
                chk(f'{tag} L={L}: shouldHint = true (clause 3 holds)', r['shouldHint'])
                chk(f'{tag} L={L}: queued + rejected = 2000 ({r["queued"]} + {r["rejected"]})', r['queued'] + r['rejected'] == 2000)
                if b == 'orig':
                    chk(f'{tag} L={L}: queued = 2000, rejected = 0 (B2f orig)', r['queued'] == 2000 and r['rejected'] == 0)
                    chk(f'{tag} L={L}: perDest = 0 and same = false (A3.3 trace) ({r["perDest"]}, {r["same"]})', r['perDest'] == 0 and not r['same'])
                    chk(f'{tag} L={L}: heapDeltaMiB ≈ 125 ± 30 ({r["heapMiB"]})', 95 <= r['heapMiB'] <= 155)
                else:
                    q = min(L + 1, 2000)
                    chk(f'{tag} L={L}: queued = min(L+1, 2000) = {q} ({r["queued"]}), rejected = {2000 - q} ({r["rejected"]})',
                        r['queued'] == q and r['rejected'] == 2000 - q)
                    chk(f'{tag} L={L}: perDest = queued and same = true ({r["perDest"]}, {r["same"]})', r['perDest'] == q and r['same'])
                    exp = q * 65536 / 2 ** 20
                    if L == 1:
                        chk(f'{tag} L=1: heapDeltaMiB < 10 ({r["heapMiB"]})', r['heapMiB'] < 10)
                    else:
                        chk(f'{tag} L={L}: heapDeltaMiB ≈ queued × 64 KiB = {exp:.0f} MiB ± 30 ({r["heapMiB"]})', abs(r['heapMiB'] - exp) <= 30)
            if b == 'orig':
                hs = [r['heapMiB'] for r in res]
                chk(f'{tag}: heap independent of L (max − min = {max(hs) - min(hs)} MiB ≤ 30)', max(hs) - min(hs) <= 30)
    # cross-build relation (B2g row 1 vs rows 2-6)
    o = unit_lines(f'{ROOT}/run1/unit-orig/ant.log')[1]
    f = unit_lines(f'{ROOT}/run1/unit-fixed/ant.log')[1]
    chk('B2g row 1: orig rejects nothing at any L while fixed queued follows min(L+1, 2000)',
        all(r['rejected'] == 0 for r in o) and [r['queued'] for r in f] == [2, 129, 1001, 2000])
    chk('B2g row 6 not needed: heap differs between fixed L=1 and MAX by > 100 MiB '
        f'({f[0]["heapMiB"]} vs {f[3]["heapMiB"]})', f[3]['heapMiB'] - f[0]['heapMiB'] > 100)
    chk('repeat agrees exactly on queued/rejected/perDest/same for both builds',
        all([(r['queued'], r['rejected'], r['perDest'], r['same']) for r in unit_lines(f'{ROOT}/run1/unit-{b}/ant.log')[1]] ==
            [(r['queued'], r['rejected'], r['perDest'], r['same']) for r in unit_lines(f'{ROOT}/run1-rep2/unit-{b}/ant.log')[1]]
            for b in ('orig', 'fixed')))


# ------------------------------------------------------------------ cluster tier
RUNS = {'O-1': ('O', 1), 'O-128': ('O', 128), 'O-MAX': ('O', MAX), 'F-1': ('F', 1), 'F-MAX': ('F', MAX)}


def cluster():
    print('== cluster tier (B3f / B3g)')
    C = {}
    for run, (b, L) in RUNS.items():
        d = f'{ROOT}/run1/cluster/{run}'
        rows = []
        for l in open(d + '/samples.csv').read().splitlines()[1:]:
            p = l.split(',')
            if len(p) == 6 and all(x.lstrip('-').isdigit() for x in p):
                rows.append(list(map(int, p)))
        og = [list(map(int, l.split(','))) for l in open(d + '/oldgen.csv').read().splitlines()
              if re.match(r'^\d+,\d+,\d+$', l)]
        so = open(d + '/stress-main.out', errors='replace').read()
        res = so[so.rfind('Results:'):]
        terr = int(re.search(r'Total errors\s*:\s*([\d,]+)', res).group(1).replace(',', ''))
        tpar = int(re.search(r'Total partitions\s*:\s*([\d,]+)', res).group(1).replace(',', ''))
        warm = int(re.search(r'Warming up WRITE with (\d+) iterations', so).group(1))
        totals = [int(x) for x in re.findall(r'Too many in flight hints: (\d+)', so)]
        logl = sum(open(f'{d}/n1-logs/{f}', errors='replace').read().count('Too many in flight hints') for f in ('system.log', 'debug.log'))
        down = open(f'{d}/n1-logs/system.log', errors='replace').read().count('/127.0.0.22:7000 is now DOWN')
        ydiff = open(d + '/n1-yaml.diff').read()
        summ = open(d + '/summary.txt').read()
        bef = re.search(r"before: \{'TotalHints': '(\d+)', 'Count': '(\d+)'", summ)
        aft = re.search(r"after \(\+30 s\): \{'TotalHints': '(\d+)', 'Count': '(\d+)'", summ)
        hb = int(re.search(r'n1 hints: (\d+) B', summ).group(1))
        field = re.search(r'build check.*cache\.(\w+)<', summ).group(1)
        c = dict(L=L, rows=rows, og=og, terr=terr, tpar=tpar, warm=warm, totals=totals, logl=logl, down=down,
                 hints_delta=int(aft.group(1)) - int(bef.group(1)), una_delta=int(aft.group(2)) - int(bef.group(2)), hb=hb)
        c['max_hip'] = max(r[2] for r in rows)
        c['max_pend'] = max(r[3] for r in rows)
        c['max_old'] = max(r[2] for r in og) if og else 0
        C[run] = c
        t = run
        chk(f'{t}: build field {field} ({"CacheLoader" if b == "O" else "LoadingCache"} expected)', field == ('CacheLoader' if b == 'O' else 'LoadingCache'))
        chk(f'{t}: yaml diff has concurrent_writes 2, n1 address, JMX 7221', all(s in ydiff for s in ('> concurrent_writes: 2', '> listen_address: 127.0.0.21', '> JMX_PORT="7221"')))
        chk(f'{t}: sampler rows {len(rows)} ≥ 150 (≥ 30 s at 200 ms), limit column = {L} in every row', len(rows) >= 150 and all(r[1] == L for r in rows))
        chk(f'{t}: n1 saw n2 DOWN once ({down})', down == 1)
        chk(f'{t}: stress partitions = 1,000,000 and warm-up 50,000 ({tpar}, {warm})', tpar == 1000000 and warm == 50000)
        chk(f'{t}: hints created + Unavailables = all 1,050,000 writes ({c["hints_delta"]} + {c["una_delta"]})', c['hints_delta'] + c['una_delta'] == 1050000)
        chk(f'{t}: sampler last Unavailables = JMX after-before ({rows[-1][4] - rows[0][4]} vs {c["una_delta"]})', rows[-1][4] - rows[0][4] == c['una_delta'])
        chk(f'{t}: bytes per hint on disk 1,090–1,100 B ({hb / c["hints_delta"]:.1f})', 1090 <= hb / c['hints_delta'] <= 1100)
        chk(f'{t}: "Too many in flight hints" lines in n1 logs = 0 (R5) ({logl})', logl == 0)
        if b == 'O' or L == MAX:
            chk(f'{t}: Unavailables delta = 0 and stress errors = 0 ({c["una_delta"]}, {terr}); no message in stress output ({len(totals)})',
                c['una_delta'] == 0 and terr == 0 and not totals)
            chk(f'{t}: max hintsInProgress ≥ 2 ({c["max_hip"]})', c['max_hip'] >= 2)
            if L < MAX:
                n_above = sum(1 for r in rows if r[2] > L)
                chk(f'{t}: hintsInProgress above L = {L} in {n_above} samples (max {c["max_hip"]}): clause 1 was true while nothing was refused', n_above > 0)
            chk(f'{t}: hints on disk 1.0–1.3 GB ({hb})', 1.0e9 <= hb <= 1.3e9)
        else:
            chk(f'{t}: Unavailables delta > 0 ({c["una_delta"]}) and stress errors > 0 ({terr})', c['una_delta'] > 0 and terr > 0)
            chk(f'{t}: Unavailables − stress main errors ≤ warm-up writes ({c["una_delta"] - terr} ≤ {warm})', 0 <= c['una_delta'] - terr <= warm)
            chk(f'{t}: stress prints the refusal text, twice per failed write ({len(totals)} = 2 × {c["una_delta"]})', len(totals) == 2 * c['una_delta'])
            chk(f'{t}: max hintsInProgress ≤ 130 ({c["max_hip"]}); operand re-read in the messages: max {max(totals)}', c['max_hip'] <= 130)
    O = [C[k] for k in ('O-1', 'O-128', 'O-MAX')]
    for key, lab in (('max_hip', 'peak hintsInProgress'), ('max_pend', 'peak MutationStage pending'), ('max_old', 'peak old-gen use')):
        v = [o[key] for o in O]
        chk(f'B3f O-*: {lab} within ±25 % ({v})', max(v) <= 1.25 * min(v))
    chk(f'B3f O-MAX: max hintsInProgress > 128 ({C["O-MAX"]["max_hip"]})', C['O-MAX']['max_hip'] > 128)
    chk(f'B3f O-1 vs O-MAX hint bytes ±5 % ({C["O-1"]["hb"]} vs {C["O-MAX"]["hb"]})', abs(C['O-1']['hb'] / C['O-MAX']['hb'] - 1) <= 0.05)
    chk(f'B3f F-1 hints well below O-1 (ratio {C["F-1"]["hb"] / C["O-1"]["hb"]:.3f})', C['F-1']['hb'] < 0.75 * C['O-1']['hb'])
    chk(f'B3f F-1 peak pending below O-1 ({C["F-1"]["max_pend"]} vs {C["O-1"]["max_pend"]})', C['F-1']['max_pend'] < C['O-1']['max_pend'])
    chk(f'B3f F-MAX matches O-MAX: hip, pending, hint bytes ({C["F-MAX"]["max_hip"]}/{C["O-MAX"]["max_hip"]}, '
        f'{C["F-MAX"]["max_pend"]}/{C["O-MAX"]["max_pend"]}, {C["F-MAX"]["hb"]}/{C["O-MAX"]["hb"]})',
        C['F-MAX']['max_hip'] == C['O-MAX']['max_hip'] and C['F-MAX']['max_pend'] == C['O-MAX']['max_pend'] and C['F-MAX']['hb'] == C['O-MAX']['hb'])
    r = C['F-MAX']['max_old'] / C['O-MAX']['max_old']
    chk(f'B3f F-MAX peak heap matches O-MAX, old-gen use within ±25 % ({C["F-MAX"]["max_old"]} vs {C["O-MAX"]["max_old"]}, ratio {r:.2f})', 0.8 <= r <= 1.25)
    hu = (max(x[5] for x in C['F-MAX']['rows']), max(x[5] for x in C['O-MAX']['rows']))
    chk(f'(extra) F-MAX vs O-MAX peak heapUsed from the 200 ms sampler within ±25 % ({hu[0]} vs {hu[1]})', 0.8 <= hu[0] / hu[1] <= 1.25)


unit()
cluster()
print(f'TOTAL ok={TOT["ok"]} FAIL={TOT["FAIL"]}')
