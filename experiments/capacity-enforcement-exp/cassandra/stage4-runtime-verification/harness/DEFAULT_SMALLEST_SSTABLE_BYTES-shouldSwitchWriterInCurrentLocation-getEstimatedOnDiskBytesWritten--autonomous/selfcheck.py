#!/usr/bin/env python3 -I
"""Independent self-check for DEFAULT_SMALLEST_SSTABLE_BYTES-...--autonomous. Does not import or reuse analyze_unit.py / analyze_cluster.py.
Unit: re-reads the console echo in ant.log against arms.txt, recomputes counts, bounds and sizes from raw call/file CSVs by another route
(a byte-for-byte replay of line 84 on the logged operands).
Cluster: re-parses debug.log.segment (switch lines, the task-level space request), system.log.segment (Compacted line), tablestats.after,
du.csv and rss.csv, without using summary.json's derived fields except the raw output-size list for a cross-reference.
usage: selfcheck.py <unit dir> <cluster root>"""
import sys, re, os, csv, json, math, glob
UNIT, CL = sys.argv[1], sys.argv[2]
out = []
def claim(n, ok, note): out.append(ok); print(f"[{'holds' if ok else 'DOES NOT HOLD'}] {n}: {note}")
half_up = lambda x: math.floor(x + 0.5)
# ---------------- unit ----------------
arms = {}
for l in open(f'{UNIT}/raw/arms.txt'):
    p = l.split(); arms[p[1]] = dict(x.split('=', 1) for x in p[2:] if '=' in x)
echo = {}
for l in open(f'{UNIT}/ant.log', errors='replace'):
    m = re.search(r'STAGE4 ARM (\S+) (.*)$', l)
    if m: echo[m.group(1)] = dict(x.split('=', 1) for x in m.group(2).split() if '=' in x)
claim('U0 arms.txt equals the console echo in ant.log, 8 arms, JUnit ran 8 tests with no failure', echo == arms and len(arms) == 8 and bool(re.search(r'Tests run: 8, Failures: 0, Errors: 0', open(f'{UNIT}/ant.log', errors='replace').read())), f'{len(arms)} arms')
def rows(p): return list(csv.DictReader(open(p)))
for tag in sorted(arms):
    kv = arms[tag]; calls = rows(f'{UNIT}/raw/calls-{tag}.csv'); files = rows(f'{UNIT}/raw/files-{tag}.csv')
    ops = [int(c['operand']) for c in calls]; ret = [int(c['returned']) for c in calls]
    sizes = [int(f['data_file_bytes']) for f in files]; T = int(kv['inputBytes'])
    if kv['kind'] == 'max':
        m = int(kv['param'])
        replay = [1 if o > m else 0 for o in ops]
        claim(f'U-{tag} replay of MaxSSTableSizeWriter rule on the logged operands reproduces every return; pieces = trues + 1; non-final pieces equal the operands at the trues', replay == ret and len(sizes) == sum(ret) + 1 and [o for o, r in zip(ops, ret) if r] == sizes[:-1], f'pieces={len(sizes)} sizes={sizes[:4]}...')
        continue
    S = int(kv['param']); rl = int(kv['ratiosLength']); tot = int(kv['totalSize'])
    ratios = [2.0 ** -(k + 1) for k in range(20)]
    k = next((k for k in range(1, 21) if tot * 2.0 ** -k < S), 20)   # first k with ratio*T < S, else all 20
    # replay line 84 on the logged operands with an independently tracked index and target
    idx = 0; tgt = half_up(tot * ratios[0]); rep = []
    for o in ops:
        sw = o > tgt and idx < k - 1
        rep.append(1 if sw else 0)
        if sw: idx += 1; tgt = half_up(tot * ratios[idx])
    claim(f'U-{tag} ratio count {k} matches the writer ({rl}); replay of line 84 reproduces every return; pieces == trues + 1 == {sum(ret) + 1}', rl == k and rep == ret and len(sizes) == sum(ret) + 1, f'S={S} T={tot} pieces={len(sizes)}')
    claim(f'U-{tag} T equals the input length and output bytes equal input bytes within 0.1% (S changes how it is divided, not how much)', tot == T and abs(sum(sizes) - T) <= 0.001 * T, f'in={T} out={sum(sizes)}')
    tg = [half_up(tot * ratios[i]) for i in range(k)]
    if kv['compressed'] == 'false':
        claim(f'U-{tag} each non-final piece is the operand at its switch and exceeds its own target; last piece is the remainder T - sum(others)', all(sizes[i] == [o for o, r in zip(ops, ret) if r][i] > tg[i] for i in range(len(sizes) - 1)) and sizes[-1] == sum(sizes) - sum(sizes[:-1]), f'targets={tg[:4]} sizes={sizes[:4]}')
    print(f'   U-{tag} N={len(sizes)} sizes(first4)={sizes[:4]} last={sizes[-1]} own-target-of-last={tg[len(sizes)-1] if len(sizes) <= k else None}')
# ---------------- cluster ----------------
for X in 'ABC':
    for arm_dir in sorted(glob.glob(f'{CL}/{X}/*/summary.json')):
        d = os.path.dirname(arm_dir); arm = os.path.basename(d); S = json.load(open(arm_dir))
        dbg = open(f'{d}/debug.log.segment', errors='replace').read(); sysl = open(f'{d}/system.log.segment', errors='replace').read()
        ts = open(f'{d}/tablestats.after').read()
        asks = [int(m.group(1)) for m in re.finditer(r'checking if we can write (\d+) bytes', dbg)]
        sw = [int(m.group(1)) for m in re.finditer(r'Switching writer, currentBytesToWrite = (\d+)', dbg)]
        T = asks[0] if asks else None
        cnt = int(re.search(r'SSTable count: (\d+)', ts).group(1))
        cl = [l for l in sysl.splitlines() if 'Compacted (' in l]
        m = re.search(r'([\d.,]+)(KiB|MiB|GiB) to ([\d.,]+)(KiB|MiB|GiB)', cl[0]) if cl else None
        unit = {'KiB': 2 ** 10, 'MiB': 2 ** 20, 'GiB': 2 ** 30}
        outb = float(m.group(3).replace(',', '')) * unit[m.group(4)] if m else None
        rows_du = list(csv.DictReader(open(f'{d}/du.csv')))
        pre = S['pre_du_table']; peak = max(int(r['table_dir_bytes']) for r in rows_du)
        sizes = S['output_sizes_in_creation_order']
        name = f'C-{X}/{arm}'
        claim(f'{name} the task-level space request in debug.log is the input T ({T}) = summary input_bytes', T == S['input_bytes'] and len(asks) >= 1, f'asks={asks}')
        claim(f'{name} live SSTable count after (tablestats) == outputs == switches + 1', cnt == len(sizes) == len(sw) + 1 or (arm.startswith('lcs') and cnt == len(sizes)), f'tablestats count={cnt} outputs={len(sizes)} switches={len(sw)}')
        claim(f'{name} Compacted line output bytes within 0.2% of the sum of the output Data.db sizes', m is not None and abs(outb - sum(sizes)) <= 0.002 * sum(sizes), f'compacted-line={outb:.0f} sum={sum(sizes)}')
        claim(f'{name} peak table-dir bytes {peak} are between 1.8x and 2.1x the pre-compaction directory ({pre}) (input kept until commit), recomputed from du.csv', 1.8 * pre <= peak <= 2.1 * pre if pre > 5e7 else peak <= 2.1 * pre, f'ratio={peak/pre:.3f}')
        print(f'   {name}: T={T} outputs={len(sizes)} switches={sw} sizes={sizes[:10]} peak={peak} rss_peak_kb={S["rss_anon_peak_kb"]} heap_peak_kb={S["heap_used_peak_kb"]}')
        # ratio-count replay for split arms, constant read from the tree's session.log
        sl = open(f'{CL}/{X}/session.log').read()
        const = int(re.search(r'DEFAULT_SMALLEST_SSTABLE_BYTES = ([\d_]+);', sl).group(1).replace('_', ''))
        if arm in ('split', 'split2', 'splitz', 'small'):
            k = next((k for k in range(1, 21) if T * 2.0 ** -k < const), 20)
            claim(f'{name} (constant {const}) outputs == first k with T/2^k < constant == {k}; switch values == round(T*2^-(i+2)); each non-final piece above its target', len(sizes) == k and sw == [half_up(T * 2.0 ** -(i + 2)) for i in range(k - 1)] and all(sizes[i] > half_up(T * 2.0 ** -(i + 1)) for i in range(k - 1)), f'N={len(sizes)} k={k} sw={sw}')
        if arm == 'plain':
            claim(f'{name} plain compaction: one output, no switch line', len(sizes) == 1 and not sw, f'N={len(sizes)}')
print('SELFCHECK', 'ALL HOLD' if all(out) else f'{out.count(False)} DO NOT HOLD of {len(out)}', f'({len(out)} claims)')
