#!/usr/bin/env python3
"""Independent self-check (own parsers; does not import the analyzers) for transition-bytes-collector-add-buffer-length--autonomous.
usage: selfcheck.py unit <unit dir> | cluster <cluster dir>"""
import glob, json, os, re, sys
mode, d = sys.argv[1], sys.argv[2]
fails = 0
def ok(c, msg):
    global fails
    print(('PASS ' if c else 'FAIL ') + msg)
    if not c: fails += 1
if mode == 'unit':
    kv = lambda l: dict(x.split('=', 1) for x in l.split()[2:] if '=' in x)
    seen = {}
    n_sa = n_wk = n_it = 0
    for f in sorted(glob.glob(d + '/tc-unit*.txt')):
        for l in open(f):
            if l.startswith('TC standalone') and 'thr=none' not in l:
                m = kv(l); L = int(m['L']); cap = int(m['cap']); n_sa += 1
                seen.setdefault(L, set()).add(cap)
                ok((cap == 32) if L <= 32 else (L <= cap <= L + L // 8 + 10), f"{os.path.basename(f)} standalone L={L} cap={cap} in band") if not (cap == 32 if L <= 32 else L <= cap <= L + L // 8 + 10) else None
            elif l.startswith('TC walker'):
                m = kv(l); n_wk += 1
                lo, hi, a = int(m['lower']), int(m['upper']), int(m['alloc_per_call'])
                if not (lo <= a <= hi and m['result_equals_key'] == 'true'): ok(False, f"walker row out of bounds {l.strip()}")
            elif l.startswith('TC iterator'):
                m = kv(l); n_it += 1
                if int(m['cap']) != int(m['sim_cap']): ok(False, f"iterator cap {l.strip()}")
    ok(all(len(v) == 1 for v in seen.values()) and set(seen) == {8, 32, 33, 1024, 8192, 65535}, f'one capacity per L over {n_sa} standalone readings in all files: {({L: sorted(v) for L, v in sorted(seen.items())})}')
    ok(n_wk >= 3 * 3 * 6 * 2 * 3 and n_it >= 3 * 3 * 6, f'readings counted: walker {n_wk}, iterator {n_it}')
    # independent recomputation of the library growth
    def grow(n):  # Lucene 9.7.0 ArrayUtil.oversize for 1-byte elements on 64-bit
        extra = max(n >> 3, 3); s = n + extra; return (s + 7) & ~7
    for L in (33, 1024, 8192, 65535):
        c = 32
        for p in range(L):
            if p == c: c = grow(p + 1)
        ok(c in seen.get(L, set()), f'independent growth recomputation L={L}: {c}')
    gr = [l for f in glob.glob(d + '/tc-unit.txt') for l in open(f) if l.startswith('TC guardrail')]
    for l in gr:
        thr = {'1KiB': 1024, '8KiB': 8192, '64KiB': 65536}[re.search(r'thr=(\S+)', l).group(1)]
        for k, v in re.findall(r'\b(\d+)=(FAIL|ok)\b', l):
            if (int(k) > thr) != (v == 'FAIL'): ok(False, f'guardrail {l.strip()[:80]} {k}={v}')
    ok(len(gr) == 3, f'guardrail control rows {len(gr)}')
    ok(len(glob.glob(d + '/tc-unit*.txt')) == 3, 'three output files (ant, -Xmx256m, -Xmx512m)')
    xm = {f: re.search(r'xmx=(\d+)', open(f).readline()).group(1) for f in glob.glob(d + '/tc-unit*.txt')}
    ok(sorted(int(v) for v in xm.values())[0] < 300e6 and sorted(int(v) for v in xm.values())[1] < 600e6 and sorted(int(v) for v in xm.values())[2] > 900e6, f'JVM max memory differed across the three runs: {sorted(int(v) for v in xm.values())}')
else:
    LIVES = ['T1k', 'T8k', 'T64k', 'BIG']
    for L in LIVES:
        tr = open(f'{d}/{L}/trace.txt', errors='replace').read().splitlines()
        ok(not any('COLL' in l for l in tr), f'{L}: trace has {len(tr)} lines, no line containing COLL')
        ok(any(l.startswith('LIVE saireader') for l in tr) and any(l.startswith('LIVE walker') for l in tr), f'{L}: LIVE walker and saireader lines present')
        y = open(f'{d}/{L}/cassandra.yaml').read()
        thr = {'T1k': '1KiB', 'T8k': '8KiB', 'T64k': '64KiB', 'BIG': '8KiB'}[L]; fmt = 'big' if L == 'BIG' else 'bti'
        ok(f'sai_string_term_size_fail_threshold: {thr}' in y and f'selected_format: {fmt}' in y, f'{L}: yaml has threshold {thr} and format {fmt}')
        sl = open(f'{d}/{L}/system.log', errors='replace').read()
        bad = [l for l in sl.splitlines() if (l.startswith('ERROR') and 'Guardrail sai_string_term_size violated' not in l) or ('java.lang.OutOfMemoryError' in l)]
        gl = [l for l in sl.splitlines() if l.startswith('ERROR') and 'Guardrail sai_string_term_size violated' in l]
        ok(not bad, f'{L}: system.log segment has no ERROR/OOM line other than the guardrail rejection line ({len(gl)} of those, expected only where a table was rejected)')
        ok('byteman' in sl.lower() or 'javaagent' in sl.lower(), f'{L}: system.log JVM arguments mention the Byteman agent')
        m = re.search(r'-Xmx(\w+)', sl)
        ok(bool(m) and m.group(1).lower() in ('1g', '1024m'), f'{L}: -Xmx {m.group(1) if m else None}')
        ok(len(glob.glob(f'{d}/{L}/histo-*')) >= 7, f'{L}: {len(glob.glob(f"{d}/{L}/histo-*"))} histogram files')
    # acceptance matrix recomputed from the session log / cells
    cells = [json.loads(l) for l in open(d + '/cells.jsonl')]
    thr_b = {'T1k': 1024, 'T8k': 8192, 'T64k': 65536, 'BIG': 8192}
    vl = {'w1': 900, 'w2': 8191, 'w3': 900, 'w4': 40960}
    for r in cells:
        if r['kind'] == 'phase' and r['phase'].startswith('load_'):
            t = r['phase'][5:]; x = r['detail']; allow = vl[t] <= thr_b[r['life']]
            good = (x['ok'] == x['expected'] and x['rejected'] == 0) if allow else (x['ok'] == 0 and x['rejected'] == x['expected'])
            ok(good and x['other_errors'] == 0, f"{r['life']} {t}: v={vl[t]} vs threshold {thr_b[r['life']]} -> {'accepted' if allow else 'rejected'}; ok={x['ok']} rejected={x['rejected']} of {x['expected']}")
    left = os.popen("ps -eo pid,args | grep -E 'java .*CassandraDaemon' | grep 's4-b7-tc-run' | grep -v grep").read()
    ok(left.strip() == '', 'no CassandraDaemon of this harness left running')
print('SELFCHECK', 'ALL PASS' if fails == 0 else f'{fails} FAIL')
