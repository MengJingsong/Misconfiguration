#!/usr/bin/env python3
"""Evaluates B3f (as amended) from a cluster run directory: analyze-cluster.py <dir> <rows>. Prints EXPECTED lines and a SUMMARY."""
import csv, re, sys
D = sys.argv[1]; rows = int(sys.argv[2])
summ = open(D + '/summary.txt').read()
peak = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', re.search(r'peak du \(bytes\): (.*)', summ).group(1))}
rat = {}
for r in csv.DictReader(open(D + '/ratios.csv')):
    rat[(r['when'], r['table'])] = [float(x) for x in r['ratios'].split()] if r['ratios'] else []
    rat[(r['when'] + '-du', r['table'])] = int(r['du'])
du = list(csv.reader(open(D + '/du.csv')))
hdr, last = du[0], [int(x) for x in du[-1]]
endu = dict(zip(hdr[1:], last[1:]))
mid = {c: [int(r[i + 1]) for r in du[1:]] for i, c in enumerate(hdr[1:])}
frac = {n: endu[n] / peak[n] for n in peak}
log = ''
for fn in ('system.log',):
    try:
        log += open(D + '/' + fn).read()
    except OSError:
        pass
comp = {n: len(re.findall(r'Compacted \(.*?\) \d+ sstables to \[[^\]]*/ks/%s-' % n, log)) for n in peak}
ok = {}
def exp(key, desc, cond):
    ok[key] = bool(cond)
    print(f'EXPECTED: {key} {desc} — {"yes" if cond else "NO"}')
A = ['a05', 'a20', 'a40', 'a70', 'a150', 'adef']; B = ['b05', 'b20', 'b40', 'b70', 'b150']
r0 = lambda n: max(rat[('before-enable', n)] or [float('nan')])
exp('R1', 'ratio before enable: group A, adef, gi, go, pc in 0.4-0.6 (%s)' % ' '.join(f'{n}:{r0(n):.3f}' for n in A + ['gi', 'go', 'pc']), all(0.4 <= r0(n) <= 0.6 for n in A + ['gi', 'go', 'pc']))
exp('R2', 'ratio before enable: group B in 0.1-0.2 (%s)' % ' '.join(f'{n}:{r0(n):.3f}' for n in B), all(0.1 <= r0(n) <= 0.2 for n in B))
comp_t = ['a05', 'a20', 'a40', 'adef']
exp('C1', 'a05, a20, a40, adef: du at window end = 0.42-0.58 of peak (%s)' % ' '.join(f'{n}:{frac[n]:.3f}' for n in comp_t), all(0.42 <= frac[n] <= 0.58 for n in comp_t))
exp('C2', 'b05: du at window end = 0.77-0.93 of peak (%.3f)' % frac['b05'], 0.77 <= frac['b05'] <= 0.93)
hold = ['a70', 'a150', 'b20', 'b40', 'b70', 'b150', 'gi', 'go']
exp('H1', 'a70, a150, b20, b40, b70, b150, gi, go stay within 2%% of peak through the window (min over samples: %s)' % ' '.join(f'{n}:{min(mid[n]) / peak[n]:.3f}' for n in hold), all(min(mid[n]) / peak[n] >= 0.98 for n in hold))
exp('H2', 'gi and go: ratio after the window still 0.4-0.6, ten times X=0.05 (gi %s, go %s)' % (rat[('after-window', 'gi')], rat[('after-window', 'go')]),
    all(0.4 <= max(rat[('after-window', n)]) <= 0.6 for n in ('gi', 'go')))
sc = eval(re.search(r'after the flush: (\{.*?\})', summ).group(1))
exp('H3', 'system.log "Compacted" lines per table (one per sstable that compacted; pc: its one(s) are the manual nodetool compact); sstables per table after the flush: ' + ' '.join(f'{n}={sc[n]}' for n in sorted(sc)) + ' | compactions: ' + ' '.join(f'{n}={comp[n]}' for n in sorted(comp)),
    all(comp[n] == sc[n] for n in comp_t + ['b05']) and all(comp[n] == 0 for n in hold) and comp['pc'] == 1)
exp('K1', 'pc: du at window end within 2%% of peak (%.3f), then after nodetool compact 0.42-0.58 (%.3f)' % (frac['pc'], rat[('after-compact-du', 'pc')] / peak['pc']),
    frac['pc'] >= 0.98 and 0.42 <= rat[('after-compact-du', 'pc')] / peak['pc'] <= 0.58)
vals = [frac[n] for n in comp_t]
exp('S1', 'end sizes of a05, a20, a40, adef agree within 0.08 (max-min %.3f)' % (max(vals) - min(vals)), max(vals) - min(vals) <= 0.08)
print('SUMMARY: ' + ' '.join(f'{k}={"ok" if v else "NO"}' for k, v in ok.items()))
