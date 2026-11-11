#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files of block_size-writeposting-blocksize--autonomous (regexes on the raw text; does not import analyze_*.py).
usage: selfcheck.py <unit-dir> [<cluster-root>]"""
import glob, math, os, re, sys

bad = 0


def chk(name, ok, detail=''):
    global bad
    print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + detail if detail else ''))
    bad += (not ok)


ud = sys.argv[1]
outs = sorted(glob.glob(ud + '/bs*.out'))
chk('unit: 30 cell outputs (2 reps x 3 sizes x 5 cells)', len(outs) == 30, str(len(outs)))
s = open(ud + '/summary.txt').read()
chk('unit: all cells exit 0, upstream PostingsTest passed, no daemon left', s.count('exit=0') >= 31 and 'Failures: 0, Errors: 0' in s and 'no CassandraDaemon' in s)
data = {}
for f in outs:
    t = open(f).read()
    m = re.search(r'bs=(\d+) N=(\d+) stride=(\d+) lists=(\d+) label=(\S+) writeAlloc=\d+ dataBytes=(\d+)', t)
    ctor = int(re.search(r'ctorAlloc=(\d+)', t).group(1))
    bs, n, st, ls, lab, db = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5), int(m.group(6))
    chk(f'unit {lab}: constructor allocates the 8bs+16 deltaBuffer', 8 * bs + 16 <= ctor <= 8 * bs + 16 + 4000, str(ctor))
    if st == 3:
        nb = -(-n // bs)
        model = ls * (1 + nb * (1 + -(-bs * 2 // 8)))
        chk(f'unit {lab}: data bytes == block model ({model})', abs(db - model) <= 0.02 * model, str(db))
    data[(bs, n, st, ls, lab[-2:])] = db
for bs in (16, 128, 1024):
    a, b, c = (data[(bs, n, 3, 1, 'r1')] for n in (1000, 100000, 1000000))
    chk(f'unit bs={bs}: data bytes strictly increase with N and scale ~linearly (1M/100k in 9.5..10.5)', a < b < c and 9.5 <= c / b <= 10.5, f'{a} {b} {c}')
    chk(f'unit bs={bs}: wide-stride control raises bytes per posting >4x', data[(bs, 100000, 1000003, 1, 'r1')] > 4 * b)
if len(sys.argv) > 2:
    cr = sys.argv[2]
    arms = {'P128-3M': 128, 'P128b-3M': 128, 'P128-750k': 128, 'ctl-seg16': 128, 'P32-3M': 32, 'P512-3M': 512}
    tot = {}
    for lab, bs in arms.items():
        led = [l.split() for l in open(f'{cr}/{lab}/ledger.txt') if l.startswith('PW')]
        chk(f'cluster {lab}: every PW ledger line has deltaBuffer {bs}', led and {int(x[1]) for x in led} == {bs}, f'{len(led)} lines')
        fl = open(f'{cr}/{lab}/files-{lab}-after-build.txt').read()
        tot[lab] = (sum(int(m.group(2)) for m in re.finditer(r'(\S+PostingLists\.db)\t(\d+)', fl)), sum(int(l.split('\t')[1]) for l in fl.splitlines() if '\t' in l))
        seg = open(cr + '/summary.txt').read().split(f'ARM {lab} start')[1].split(f'ARM {lab} STOPPED')[0]
        chk(f'cluster {lab}: VERIFY OK', 'VERIFY count' in seg and re.search(r'VERIFY.* OK\s*$', seg, re.M) is not None)
    p = lambda l: tot[l][0]
    d32, d512 = p('P32-3M') / p('P128-3M') - 1, p('P512-3M') / p('P128-3M') - 1
    chk(f'cluster: frozen criterion "PostingLists bytes of P32 and P512 within 5 percent of P128" is NOT met (P32 {100 * d32:+.1f} percent, P512 {100 * d512:+.1f} percent): confirms the analyze_cluster MISMATCH', not (abs(d32) <= 0.05 and abs(d512) <= 0.05), f"{p('P32-3M')} {p('P128-3M')} {p('P512-3M')}")
    tt = lambda lab: tot[lab][1]
    chk('cluster: total SAI bytes of P32 / P128 / P512 within 2 percent of each other (the posting files are 22 percent of the total)', max(tt('P32-3M'), tt('P128-3M'), tt('P512-3M')) <= 1.02 * min(tt('P32-3M'), tt('P128-3M'), tt('P512-3M')), f"{tt('P32-3M')} {tt('P128-3M')} {tt('P512-3M')}")
    chk('cluster: P128 and P128b (identical arms) have byte-identical posting files', p('P128-3M') == p('P128b-3M'))
    pk = lambda lab: max(int(l.split(',')[4]) for l in open(f'{cr}/{lab}/gauges-{lab}.csv').read().splitlines()[1:] if l.count(',') == 5) / 1048576
    chk('cluster: peak heap of P32 / P128 / P512 within 60 MiB of each other (2 GiB heap)', max(pk('P32-3M'), pk('P128-3M'), pk('P512-3M')) - min(pk('P32-3M'), pk('P128-3M'), pk('P512-3M')) <= 60, f"{pk('P32-3M'):.0f} {pk('P128-3M'):.0f} {pk('P512-3M'):.0f}")
    chk('cluster: PostingLists 3M / 750k in 3.4..4.6', 3.4 <= p('P128-3M') / p('P128-750k') <= 4.6, f"{p('P128-3M') / p('P128-750k'):.2f}")
    g = lambda lab: max(int(l.split(',')[1]) for l in open(f'{cr}/{lab}/gauges-{lab}.csv').read().splitlines()[1:] if l.count(',') == 5)
    chk('cluster control: 16 MiB arm peak <= 20 MiB, default arm peak > 32 MiB', g('ctl-seg16') <= 20 * 1048576 < 32 * 1048576 < g('P128-3M'), f"{g('ctl-seg16')} {g('P128-3M')}")
    fl = lambda lab: len([l for l in open(f'{cr}/{lab}/flush-lines.txt') if 'Global limit' in l])
    chk('cluster control: more memory-limit flush lines in the 16 MiB arm than the default arm (B5.8)', fl('ctl-seg16') > fl('P128-3M'), f"{fl('ctl-seg16')} vs {fl('P128-3M')}")
print(f'SELFCHECK total FAIL={bad}')
sys.exit(1 if bad else 0)
