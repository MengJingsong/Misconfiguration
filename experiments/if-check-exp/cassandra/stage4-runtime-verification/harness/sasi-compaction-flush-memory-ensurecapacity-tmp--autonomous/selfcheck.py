#!/usr/bin/env python3
"""Independent self-check: re-parses the raw files (CSV lines, Byteman trace lines, node logs, histogram jsonl) with code that does not
import the analyzers, and prints PASS/FAIL for each statement the conclusion rests on.
Usage: python3 -I selfcheck.py unit <unit-run dir>      |     python3 -I selfcheck.py cluster <cluster-run dir>"""
import sys, os, re, glob, json
res = []
def chk(name, ok, detail=''):
    res.append(ok); print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))
mode, root = sys.argv[1], sys.argv[2]

def sorts_from_trace(path):
    """per SORT_BEGIN: (alen, [tmplens incl. init], thread, t0, t1)"""
    out = []; open_by_thr = {}
    for line in open(path):
        f = line.split()
        if not f: continue
        kv = dict(x.split('=', 1) for x in f[1:] if '=' in x)
        thr = kv['thr']
        if f[0] == 'SORT_BEGIN':
            r = [int(kv['alen']), [], thr, int(kv['ms']), None]; open_by_thr[thr] = r; out.append(r)
        elif f[0] == 'SORT_END': open_by_thr[thr][4] = int(kv['ms'])
        elif f[0] in ('TMP_INIT', 'TMP_GROW'): open_by_thr[thr][1].append(int(kv['tmplen']))
    return out

if mode == 'unit':
    # ---- Part 1
    p1 = [l.strip().split(',') for l in open(root + '/cells/p1/p1.csv') if l.startswith('P1,')]
    tr = sorts_from_trace(root + '/cells/p1/trace.txt')[1:]
    chk('P1 rows == sorts after warm-up', len(p1) == len(tr), '%d vs %d' % (len(p1), len(tr)))
    allok = True
    for r, t in zip(p1, tr):
        n = int(r[2]); shape = r[3]; mx = max(t[1])
        if t[0] != n or mx > n // 2 or r[7] != 'true': allok = False
        if shape in ('ascending', 'descending') and mx != 256: allok = False
        if shape == 'random' and mx != n // 2: allok = False
    chk('P1: tmp never above a.length>>>1; ascending/descending stay at 256 longs (2 KiB); random reaches a.length>>>1 (= 4n bytes); all sorted', allok)
    # allocation of a random sort vs its final tmp (B2f: between 1x and 2x)
    for r in p1:
        if r[2] == '8388608' and r[3] == 'random' and r[4] == '1':
            ratio = int(r[6]) / (8 * 4194304)
            chk('P1 n=2^23 random: thread alloc / final tmp bytes in [1,2]', 1.0 <= ratio <= 2.0, 'ratio %.3f' % ratio)
    # ---- Part 2
    cont = {}; prefix = []
    for d in sorted(glob.glob(root + '/cells/p2_*')):
        for f in glob.glob(d + '/p2_*.csv'):
            recs = [dict(x.split('=', 1) for x in l.strip().split(',')[1:]) for l in open(f) if l.startswith('P2,')]
            tp = d + '/trace.txt'
            st = sorts_from_trace(tp) if os.path.exists(tp) else []
            if len(recs) > 1: st = st[1:]
            for i, r in enumerate(recs):
                M, L, chars, N = int(r['M_mib']), int(r['L']), int(r['chars']), int(r['N'])
                est, over = int(r['estimate']), int(r['overshoot'])
                chk('%s M=%d L=%d rep=%s: estimate crossed the limit by < 1.3 KiB (limit reached, not passed by more than one term)' % (r['mode'], M, L, r['rep']), 0 <= over < 1331 and est == (M << 20) + over and N * L == chars)
                if r['mode'] == 'CONTAINS':
                    ok = i < len(st) and st[i][0] == chars and max(st[i][1]) <= chars // 2
                    chk('CONTAINS M=%d L=%d rep=%s: the sorted array has exactly N*L elements (suffix array = 8*N*L bytes), tmp <= half' % (M, L, r['rep']), ok)
                    cont.setdefault((M, L), []).append(int(r['increment']) / chars)
                else:
                    chk('PREFIX M=%d L=%d: no LongTimSort call' % (M, L), len(st) == 0)
                    prefix.append((M, L, int(r['increment']) / (M << 20), int(r['thread_alloc_bytes']) / (M << 20)))
    # per-char increment and ratios to M
    for (M, L), v in sorted(cont.items()):
        pc = min(v)
        ratio = pc * M * 0 + pc * (M * 1048576 / (220 + L) * L) / (M * 1048576)   # increment/M from bytes per char and chars per M
        print('     CONTAINS M=%d L=%d: increment %.2f B/char (min over reps), increment/M = %.2f' % (M, L, pc, ratio))
    byL = {}
    for (M, L), v in cont.items():
        byL.setdefault(M, {})[L] = min(v) * (M * 1048576 / (220 + L) * L) / (M * 1048576)
    for M, dd in sorted(byL.items()):
        Ls = sorted(dd); mono = all(dd[a] < dd[b] for a, b in zip(Ls, Ls[1:]))
        chk('increment/M rises with L at M=%d' % M, mono, ' '.join('L=%d:%.2f' % (L, dd[L]) for L in Ls))
    chk('CONTAINS L=1000: increment >= 3x M (both M)', all(byL[M][1000] >= 3 for M in (8, 32)))
    chk('CONTAINS L=16: increment < 3x M (per-term cost dominates)', all(byL[M][16] < 3 for M in (8, 32, 128)))
    chk('PREFIX sampled increment <= 3x M in every cell', all(p[2] <= 3 for p in prefix), 'max %.2f' % max(p[2] for p in prefix))
    print('     PREFIX cumulative thread allocation / M (an upper bound on any live increment): max %.2f' % max(p[3] for p in prefix))
else:
    s = json.load(open(root + '/summary.json'))
    chk('no run error', s.get('error') is None, str(s.get('error')))
    cut = {'2': 4994, '8': 19973, '32': 79892}
    for a in s['arm_results']:
        name, mode_, cap, L = a['arm'], a['mode'], a['cap'], a['L']
        t0, t1 = a['t_compact_start'], a['t_compact_end'] + 6000
        st = sorts_from_trace(root + '/lts-trace.txt')
        win = [x for x in st if t0 <= x[3] <= t1 and x[2].startswith('SASI-General')]
        hs = [json.loads(l) for l in open(root + '/histo-%s.jsonl' % name) if l.strip()] if os.path.exists(root + '/histo-%s.jsonl' % name) else []
        hs = [h for h in hs if h.get('total_bytes')]
        base = a['baseline']['total_bytes']
        peak = max([h['total_bytes'] for h in hs], default=0)
        print('--- arm %s %s cap=%s L=%d: compact_rc=%s alive=%s windowSorts=%d histoSamples=%d inc=%.1f MiB' % (name, mode_, cap, L, a.get('compact_rc'), a.get('node_alive'), len(win), len(hs), (peak - base) / 1048576))
        seglines = open(root + '/segments-%s.txt' % name).read() if os.path.exists(root + '/segments-%s.txt' % name) else ''
        nseg = seglines.count('Flushed index segment')
        if mode_ == 'CONTAINS' and cap != 'def':
            k = cut[cap] if cap in cut else None
            if k and L == 200 and a.get('rows') == 200000:
                cuts = 200000 // k; exp = cuts + 1
                chk('%s: Flushed index segment lines == cuts + tail = %d' % (name, exp), nseg == exp, 'saw %d' % nseg)
                full = [x for x in win if x[0] == k * L]
                chk('%s: %d full segments sorted, each of exactly %d elements (8*n = %.1f MiB); tail %d' % (name, cuts, k * L, 8 * k * L / 1048576, (200000 - cuts * k) * L), len(full) == cuts and any(x[0] == (200000 - cuts * k) * L for x in win))
                chk('%s: no tmp above half the array' % name, all(max(x[1]) <= x[0] // 2 for x in win))
                chk('%s: peak live increment >= 3x M' % name, (peak - base) / 1048576 >= 3 * int(cap), '%.1f x M' % ((peak - base) / 1048576 / int(cap)))
        if mode_ == 'PREFIX':
            chk('%s: no LongTimSort call in the compaction window' % name, len(win) == 0)
            chk('%s: segment cut lines == cuts + tail' % name, nseg == 200000 // cut[cap] + 1, 'saw %d' % nseg)
        if cap == 'def' and mode_ == 'CONTAINS':
            chk('%s: option unset -> no cut line, one sort of 200000*200 elements' % name, nseg == 0 and any(x[0] == 200000 * L for x in win), 'segments %d' % nseg)
        chk('%s: log shows no OutOfMemoryError / Failed to build' % name, 'OutOfMemory' not in seglines and 'Failed to' not in seglines)
print('\nSUMMARY: %d checks, %d failed' % (len(res), len([r for r in res if not r])))
