#!/usr/bin/env python3
"""usage: selfcheck.py <run dir, e.g. ~/stage4-logs/mps2/run1>
Independent re-parse of the raw run-1 files (does NOT read summary.txt, unit-analyze output or the EXPECTED lines). Unit: the .probe lines are re-read with
its own regexes. Cluster: samples-tp.csv, samples-mem.csv, samples-jmx-<lifetime>.csv, system-<lifetime>.log, gc-<lifetime>.log, stress-*.out; phases.json
only for the time windows. Prints ok/FAIL per check with the numbers; exit 0."""
import csv, glob, json, os, re, statistics, sys
D = os.path.expanduser(sys.argv[1])
ok = fail = 0
def chk(desc, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print(('ok   ' if cond else 'FAIL ') + desc)
def med(x):
    x = list(x); return statistics.median(x) if x else float('nan')
# ------------------------------------------------------------------ unit
print('== unit ==')
sigs = []
for rep in ('rep1', 'rep2', 'rep3'):
    p = f'{D}/unit/{rep}.probe'
    if not os.path.exists(p):
        chk(f'{rep}.probe present', False); continue
    txt = open(p, errors='replace').read()
    chk(f'{rep} ended with PROBE-END', 'PROBE-END' in txt)
    rec = []
    for m in re.finditer(r'^PROBE ([AB]) n=(\d+) T=(\d+) .*? maxPool=(\d+) active=(\d+) pending=(\d+) running=(\d+) registryMiB=(\d+) .*?heapDeltaMiB=([\d.\-]+) .*?poolThreads=(\d+) .*?nmtThreadDeltaKB=(-?\d+) submitErr=(\d+) .*?maxSubmitUs=(\d+)', txt, re.M):
        v, n, T, mp, ac, pe, ru, rg, hd, pt, nmt, se, ms = m.groups()
        n, T, mp, ac, pe, ru, rg, pt, se, ms = map(int, (n, T, mp, ac, pe, ru, rg, pt, se, ms)); hd = float(hd); nmt = int(nmt)
        rec.append((v, n, mp, ac, pe, hd))
        chk(f'{rep} {v} n={n}: maxPool={n} active={ac}=min(n,T) pending={pe}=T-n', mp == n and ac == min(n, T) and pe == T - n)
        chk(f'{rep} {v} n={n}: heapDelta {hd:.1f} MiB vs {"n" if v == "A" else "T"}={n if v == "A" else T}', (abs(hd - n) <= 8) if v == 'A' else (T <= hd <= T + 8))
        chk(f'{rep} {v} n={n}: no submit error, longest execute {ms/1000:.1f} ms <= 100, pool threads {pt} <= n+8', se == 0 and ms <= 100000 and pt <= n + 8)
    chk(f'{rep}: 8 PROBE rows', len(rec) == 8)
    hs = [r[5] for r in rec if r[0] == 'B']
    if hs: chk(f'{rep} B heapDelta spread {max(hs)-min(hs):.2f} MiB <= 5', max(hs) - min(hs) <= 5)
    for m in re.finditer(r'^CTRL n=(\d+) T=600 accepted=(\d+) rejected=(\d+) queue=(\d+) active=(\d+) heapDeltaMiB=([\d.]+)', txt, re.M):
        n, acc, rej, q, ac, hd = int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), float(m[6])
        chk(f'{rep} control n={n}: queue {q}=64, accepted {acc}={n+64}, heapDelta {hd:.1f} in [{n+62},{n+72}]', q == 64 and acc == n + 64 and n + 62 <= hd <= n + 72)
    steps = {m[1]: dict(re.findall(r'(\w+)=(\d+)', m[2])) for m in re.finditer(r'^RESIZE step=\[(.*?)\] (.*)$', txt, re.M)}
    chk(f'{rep}: 8 resize steps', len(steps) == 8)
    if len(steps) == 8:
        g = lambda k, f: int(steps[k][f])
        chk(f'{rep} 4->32: active {g("set 4->32","active")}=32, listener 1, log lines 1', g('set 4->32', 'active') == 32 and g('set 4->32', 'listenerCalls') == 1 and g('set 4->32', 'resizedLogLines') == 1)
        for k in ('set 32->32 (line 384 no-op)', 'set 32->32 again'):
            chk(f'{rep} {k}: listener and log lines unchanged (1, 1)', g(k, 'listenerCalls') == 1 and g(k, 'resizedLogLines') == 1)
        k = 'set 32->8 (32 tasks running)'
        chk(f'{rep} shrink to 8: active {g(k,"active")}=32 with {g(k,"finished")} finished; listener 2, lines 2', g(k, 'active') == 32 and g(k, 'finished') == 0 and g(k, 'listenerCalls') == 2 and g(k, 'resizedLogLines') == 2)
        print('  recorded: ' + '; '.join(f'{k}: active={v["active"]} pending={v["pending"]} started={v["started"]} finished={v["finished"]}' for k, v in steps.items()))
    sigs.append([(r[0], r[1], r[2], r[3], r[4]) for r in rec])
if len(sigs) == 3: chk('reps identical in active/pending/maxPool', sigs[0] == sigs[1] == sigs[2])
# ------------------------------------------------------------------ cluster
print('== cluster ==')
C = D + '/cluster'
if not os.path.exists(C + '/phases.json'):
    print('no cluster phases'); print(f'SELFCHECK: {ok} ok, {fail} FAIL'); sys.exit(0)
PH = json.load(open(C + '/phases.json'))
def rows(path):
    try: return list(csv.DictReader(open(path)))
    except OSError: return []
TP = rows(C + '/samples-tp.csv'); MEM = rows(C + '/samples-mem.csv')
S = {}
for ph in PH:
    lab, lt = ph['label'], ph['lifetime']
    jm = []
    for r in rows(f'{C}/samples-jmx-{lt}.csv'):
        try: jm.append({k: float(v) for k, v in r.items()})
        except ValueError: pass
    r0, r1 = ph.get('r_start'), ph.get('r_end')
    inR = lambda t: r0 is not None and r0 <= t <= r1
    inW = lambda t: ph['w_start'] <= t <= ph['w_end']
    tp = [r for r in TP if r['run'] == lab]
    me = [r for r in MEM if r['run'] == lab]
    s = dict(
        act_jmx=max([max(j['rd_active'], j['mu_active']) for j in jm] or [0]), act_tp=max([max(int(r['rd_active']), int(r['mu_active'])) for r in tp] or [0]),
        rdp=med(j['rd_pending'] for j in jm if inR(j['t_ms'])), mup=med(j['mu_pending'] for j in jm if inR(j['t_ms'])),
        rdpmax=max([j['rd_pending'] for j in jm if inR(j['t_ms'])] or [0]), mupmax=max([j['mu_pending'] for j in jm if inR(j['t_ms'])] or [0]),
        heapR=med(int(r['heap_after_gc']) / 2**20 for r in me if inR(int(r['t_ms']))), heapW=med(int(r['heap_after_gc']) / 2**20 for r in me if inW(int(r['t_ms']))),
        rssR=med(int(r['rss_anon_kb']) / 1024 for r in me if inR(int(r['t_ms']))), thrR=med(j['thread_count'] for j in jm if inR(j['t_ms'])),
        rsmax=max([j['requests_size'] for j in jm if inW(j['t_ms']) or inR(j['t_ms'])] or [0]),
        mtmax=max([j['memtable_onheap'] for j in jm] or [0]) / 2**20)
    S[lab] = s
    print(f'{lab}: ' + ', '.join(f'{k}={v:.1f}' for k, v in s.items()))
    try: gc = open(f'{C}/gc-compact-{lt}.log', errors='replace').read()
    except OSError: gc = ''
    try: sl = open(f'{C}/system-{lt}.log', errors='replace').read()
    except OSError: sl = ''
    bad = [l for l in gc.splitlines() if 'Pause Full' in l and not any(c in l for c in ('System.gc()', 'Heap Inspection', 'Diagnostic Command'))]
    chk(f'{lab}: no other full GC ({len(bad)}), no OutOfMemoryError ({sl.count("OutOfMemoryError: ")}), gc log lines {len(gc.splitlines())}', not bad and 'OutOfMemoryError: ' not in sl)
    for st in ('Read', 'Mutation'):
        if ph.get('n'): chk(f'{lab}: getconcurrency {st}Stage {ph["conc_" + st + "Stage"]} = {ph["n"]}', ph['conc_' + st + 'Stage'] == ph['n'])
    for f in ('W', 'R'):
        p = f'{C}/stress-{lab}-{f}.out'
        if os.path.exists(p):
            t = open(p, errors='replace').read()
            print(f'  stress {lab}-{f}: ' + ' | '.join(re.findall(r'^(?:Op rate|Total partitions|Total errors|Total operation time)\s*:.*$', t, re.M)))
    if lab == 'RS':
        for st in ('ReadStage', 'MutationStage'):
            seq = re.findall(rf'Resized {st} maximum pool size from (\d+) to (\d+)', sl)
            chk(f'RS {st} Resized lines {seq} = [32->8, 8->64, 64->32] (none for the same-value call)', seq == [('32', '8'), ('8', '64'), ('64', '32')])
# between-lifetime checks
f3 = [l for l in ('n4', 'n32', 'n256') if l in S]
if len(f3) == 3:
    for k in ('heapR', 'heapW', 'rssR'):
        xs = [S[l][k] for l in f3]; r = max(xs) / min(xs)
        chk(f'{k} over n=4,32,256 {[round(x, 1) for x in xs]} max/min {r:.3f} <= 1.15; not (monotone and >= 1.5)', r <= 1.15 and not (xs[0] < xs[1] < xs[2] and r >= 1.5))
    chk(f'RSS(256)-RSS(4) = {S["n256"]["rssR"] - S["n4"]["rssR"]:.1f} MiB <= 64 (sub-prediction)', S['n256']['rssR'] - S['n4']['rssR'] <= 64)
    chk('load reached at n=4: median Pending in R >= 20 (rd %.0f, mu %.0f)' % (S['n4']['rdp'], S['n4']['mup']), max(S['n4']['rdp'], S['n4']['mup']) >= 20)
    big = [k for k in ('rdp', 'mup') if S['n4'][k] >= 20]
    chk(f'Pending(4) >= 5 x max(Pending(256), 1) for {big}: ' + str({k: (S['n4'][k], S['n256'][k]) for k in big}), bool(big) and all(S['n4'][k] >= 5 * max(S['n256'][k], 1) for k in big))
    for l, n in (('n4', 4), ('n32', 32), ('n256', 256)):
        chk(f'{l}: Active max {S[l]["act_jmx"]:.0f} (JMX), {S[l]["act_tp"]} (tpstats) <= {n}', S[l]['act_jmx'] <= n and S[l]['act_tp'] <= n)
    print('  threads (JMX ThreadCount median in R): ' + str({l: S[l]['thrR'] for l in f3}))
if 'n32' in S and 'n32b' in S:
    r = max(S['n32']['heapR'], S['n32b']['heapR']) / min(S['n32']['heapR'], S['n32b']['heapR'])
    chk(f'noise: HEAP(32) {S["n32"]["heapR"]:.1f} vs {S["n32b"]["heapR"]:.1f}, ratio {r:.3f} <= 1.15', r <= 1.15)
if 'PC0' in S and 'PC' in S:
    chk(f'control (i): PC RequestsSize max {S["PC"]["rsmax"]/1024:.1f} KiB <= 160 and PC0 {S["PC0"]["rsmax"]/1024:.1f} KiB >= 2 x PC', S['PC']['rsmax'] / 1024 <= 160 and S['PC0']['rsmax'] >= 2 * S['PC']['rsmax'])
if all(l in S for l in ('M64', 'M256', 'n32')):
    a, b, c = S['M64']['mtmax'], S['M256']['mtmax'], S['n32']['mtmax']
    chk(f'control (ii): peak MemtableOnHeapSize {a:.1f} <= {b:.1f}/1.3 <= {c:.1f}/1.69', a <= b / 1.3 and b / 1.3 <= c / 1.69)
    chk(f'control (ii): HEAP(W) {S["M64"]["heapW"]:.1f} < {S["M256"]["heapW"]:.1f} < {S["n32"]["heapW"]:.1f}', S['M64']['heapW'] < S['M256']['heapW'] < S['n32']['heapW'])
print(f'SELFCHECK: {ok} ok, {fail} FAIL')
