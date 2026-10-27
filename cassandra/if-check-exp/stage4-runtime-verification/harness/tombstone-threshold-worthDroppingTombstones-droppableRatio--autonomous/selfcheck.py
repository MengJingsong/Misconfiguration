#!/usr/bin/env python3
"""Independent self-check (stage 4 step 4): re-parses the RAW files of a run, not the analyzers' output.
usage: selfcheck.py unit <run-dir>/unit      |      selfcheck.py cluster <run-dir>/cluster
Unit: test.out STAGE4 lines (own parser, float32 oracle written differently) and the ant XML. Cluster: session.log (raw du and
sstablemetadata output), du.csv, system.log 'Compacted' lines and 'Flushing'/'Enqueuing' lines, schema-readback.txt."""
import glob, math, re, sys, struct
mode, d = sys.argv[1], sys.argv[2]
res = []
def chk(name, cond, note=''):
    res.append(bool(cond)); print(f'{"holds" if cond else "DOES NOT HOLD"}: {name} {note}')
def f32(x): return float(struct.unpack('<f', struct.pack('<f', float(x)))[0])
if mode == 'unit':
    L = [l.strip() for l in open(d + '/test.out') if l.startswith('STAGE4')]
    cells = []
    for l in L:
        if l.startswith('STAGE4 cell'):
            m = re.search(r'f=(\S+) gate=(\S+) X=(\S+) thr=(\S+) r=(\S+) worth=(\S+) task=(\S+) sstables=(\d+)', l)
            cells.append(m.groups())
    chk('40 cells recorded (20 open + 4 gate kinds x 5)', len(cells) == 40, f'({len(cells)})')
    # open gates: oracle  worth iff r > float(X)
    bad = [c for c in cells if c[1] == 'open' and ((c[5] == 'true') != (float(c[4]) > f32(c[2])))]
    chk('open gates: worth <=> r > float32(X) in every cell', not bad, f'(bad {len(bad)})')
    # the closed gates: no true except overlap X=0.0
    trues = [c for c in cells if c[1] in ('interval', 'neverpurge', 'overlap') and c[5] == 'true']
    chk('closed gates (interval, neverpurge, overlap) return true only for overlap at X=0.0', len(trues) == 1 and trues[0][1] == 'overlap' and trues[0][2] == '0.0', f'({[(c[1], c[2]) for c in trues]})')
    n_gated_above = [c for c in cells if c[1] in ('interval', 'overlap') and c[5] == 'false' and float(c[4]) > f32(c[2])]
    chk('closed-gate cells with r > X and worth false exist (the bypass of the threshold alone)', len(n_gated_above) >= 5, f'({len(n_gated_above)})')
    nb = [c for c in cells if c[1] == 'nooverlap' and ((c[5] == 'true') != (float(c[4]) > f32(c[2])))]
    chk('unchecked=false without overlap behaves like open', not nb)
    byt = []
    for l in L:
        m = re.match(r'STAGE4 bytes f=(\S+) X=(\S+) r=(\S+) task=(\S+) before=(\d+) after=(\d+)', l)
        if m: byt.append(m.groups())
    chk('8 byte cells', len(byt) == 8, f'({len(byt)})')
    for f, x, r, t, b, a in byt:
        if t == 'true':
            chk(f'bytes f={f} X={x}: task ran, after/before = {int(a)/int(b):.3f} vs 1-f = {1-float(f):.3f}', abs(int(a) / int(b) - (1 - float(f))) <= 0.08)
        else:
            chk(f'bytes f={f} X={x}: no task, bytes unchanged although {float(f)*100:.0f}% droppable', a == b)
    ctl = []
    for l in L:
        m = re.match(r'STAGE4 control f=(\S+) X=1.5 worth=(\S+) before=(\d+) after=(\d+)', l)
        if m: ctl.append(m.groups())
    chk('positive control: forced compaction frees (1-f) +/- 0.08 at X=1.5 while worth is false', len(ctl) == 4 and all(w == 'false' and abs(int(a) / int(b) - (1 - float(f))) <= 0.08 for f, w, b, a in ctl))
    x = open(glob.glob(d + '/TEST-*.xml')[0]).read()
    m = re.search(r'tests="(\d+)".*?errors="(\d+)".*?failures="(\d+)"', x) or re.search(r'errors="(\d+)".*?failures="(\d+)".*?tests="(\d+)"', x)
    chk('ant XML: 1 test, 0 errors, 0 failures', 'errors="0"' in x and 'failures="0"' in x and 'tests="1"' in x)
else:
    S = open(d + '/session.log').read()
    sysl = open(d + '/system.log').read()
    summ = open(d + '/summary.txt').read()
    peak = dict(re.findall(r'(\w+)=(\d+)', re.search(r'peak du \(bytes\): (.*)', summ).group(1)))
    chk('peak du recorded for 14 tables (summary.txt line written from the run\'s own du before the enable)', len(peak) == 14, f'({len(peak)})')
    du = [l.strip().split(',') for l in open(d + '/du.csv')]
    hdr = du[0][1:]; rows = [[int(x) for x in r[1:]] for r in du[1:]]
    P = {n: int(peak[n]) for n in peak}
    end = dict(zip(hdr, rows[-1]))
    chk('du.csv has samples every ~30 s over the window (>= 10 rows)', len(rows) >= 10, f'({len(rows)})')
    def sz(x):
        m = re.match(r'([\d.]+)(B|KiB|MiB|GiB)', x); return float(m.group(1)) * {'B': 1, 'KiB': 1024, 'MiB': 1024 ** 2, 'GiB': 1024 ** 3}[m.group(2)]
    comp = {}
    for m in re.finditer(r'Compacted \(\S+\) (\d+) sstables to \[\S*?/ks/(\w+?)-[0-9a-f]{32}/\S+\] to level=\d+\.\s+(\S+) to (\S+) ', sysl):
        comp.setdefault(m.group(2), []).append((int(m.group(1)), sz(m.group(3)), sz(m.group(4))))
    sc = eval(re.search(r'after the flush: (\{.*?\})', summ).group(1))
    for n in ['a05', 'a20', 'a40', 'adef', 'b05']:
        c = comp.get(n, [])
        chk(f'{n}: one single-sstable "Compacted" line per sstable ({sc[n]}), output/input = ' + ' '.join(f'{x[2]/x[1]:.3f}' for x in c), len(c) == sc[n] and all(x[0] == 1 for x in c))
    for n in ['a70', 'a150', 'b20', 'b40', 'b70', 'b150', 'gi', 'go']:
        chk(f'{n}: no "Compacted" line', n not in comp)
    chk('pc: its only "Compacted" line is after the window (the manual compact)', len(comp.get('pc', [])) == 1)
    # ratios from raw sstablemetadata output: take values the run logged
    rb = re.findall(r'ratio\[before-enable\] (\w+) \[([^\]]*)\]', S)
    ra = re.findall(r'ratio\[after-window\] (\w+) \[([^\]]*)\]', S)
    rbd = {n: [float(x) for x in v.split(',') if x.strip()] for n, v in rb}
    rad = {n: [float(x) for x in v.split(',') if x.strip()] for n, v in ra}
    chk('ratios before enable: A-group/gi/go/pc 0.4-0.6, B-group 0.1-0.2',
        all(0.4 <= max(rbd[n]) <= 0.6 for n in ['a05','a20','a40','a70','a150','adef','gi','go','pc']) and all(0.1 <= max(rbd[n]) <= 0.2 for n in ['b05','b20','b40','b70','b150']))
    chk('gi and go ratio after window still >= 0.4 (ten times 0.05)', min(max(rad['gi']), max(rad['go'])) >= 0.4, f"(gi {rad['gi']}, go {rad['go']})")
    chk('a05 and a20 and a40 and adef ratio after window ~0 (rewritten)', all(max(rad[n]) < 0.01 for n in ['a05', 'a20', 'a40', 'adef']))
    for n in ['a05', 'a20', 'a40', 'adef']:
        chk(f'{n}: end/peak {end[n]/P[n]:.3f} in 0.42-0.58', 0.42 <= end[n] / P[n] <= 0.58)
    chk(f'b05: end/peak {end["b05"]/P["b05"]:.3f} in 0.77-0.93', 0.77 <= end['b05'] / P['b05'] <= 0.93)
    for n in ['a70', 'a150', 'b20', 'b40', 'b70', 'b150', 'gi', 'go']:
        idx = hdr.index(n)
        chk(f'{n}: every sample >= 0.98 of peak', min(r[idx] for r in rows) / P[n] >= 0.98)
    chk('a05, a20, a40, adef compaction output/input within 0.42-0.58, b05 within 0.77-0.93 (from the Compacted lines, independent of du)', all(0.42 <= sum(x[2] for x in comp[n])/sum(x[1] for x in comp[n]) <= 0.58 for n in ['a05','a20','a40','adef']) and 0.77 <= sum(x[2] for x in comp['b05'])/sum(x[1] for x in comp['b05']) <= 0.93)
    m = re.search(r'pc: du before nodetool compact (\d+), after (\d+)', open(d + '/summary.txt').read())
    chk('pc: not moved by the enable, halved by nodetool compact', int(m.group(1)) / P['pc'] >= 0.98 and 0.42 <= int(m.group(2)) / P['pc'] <= 0.58, f'({m.groups()})')
    chk('the schema read-back shows all gi/go options as intended', "'tombstone_compaction_interval': '86400'" in open(d + '/schema-readback.txt').read() and "'unchecked_tombstone_compaction': 'false'" in open(d + '/schema-readback.txt').read())
    chk('no ERROR line in system.log', not re.search(r'^ERROR', sysl, re.M), f'({len(re.findall(chr(94)+"ERROR", sysl, re.M))})')
print('SELFCHECK: %d/%d hold' % (sum(res), len(res)))
