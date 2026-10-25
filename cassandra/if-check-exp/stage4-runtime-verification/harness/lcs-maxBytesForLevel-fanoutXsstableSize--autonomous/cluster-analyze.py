#!/usr/bin/env python3
"""Cluster tier analysis, lcs-maxBytesForLevel-fanoutXsstableSize--autonomous (B3f/B3g). usage: cluster-analyze.py <outdir with A B C D Aprime>"""
import sys, json, os, re
D = sys.argv[1]; MIB = 1048576
CFG = {'A': (10, 10), 'B': (160, 10), 'C': (10, 2), 'D': None, 'Aprime': (10, 10)}
def load(lb):
    d = os.path.join(D, lb); o = {}
    for t in ('lag-end', 'settled-write', 'truncated'): o[t] = json.load(open(f'{d}/snapshot-{t}.json'))
    s = [json.loads(l) for l in open(f'{d}/samples-standard1.jsonl')]
    o['samples'] = s
    st = open(f'{d}/stress-write.txt').read()
    o['errors'] = int(re.search(r'Total errors\s*:\s*(\d+)', st).group(1))
    o['rows'] = int(re.search(r'Total partitions\s*:\s*([\d,]+)', st).group(1).replace(',', ''))
    return o
def maxbytes(o):
    return max(max([x['bytes'] for x in o['samples'] if 'bytes' in x] or [0]), o['lag-end']['bytes'])
def peak_l0(o):
    v = [x['parsed']['bytes'][0] for x in o['samples'] if x.get('parsed') and x['parsed']['bytes']]
    if o['lag-end']['parsed']['bytes']: v.append(o['lag-end']['parsed']['bytes'][0])
    return max(v) if v else 0
def peak_live(o):
    v = [x['parsed']['live'] for x in o['samples'] if x.get('parsed') and x['parsed']['live']] + [o['lag-end']['parsed']['live'], o['settled-write']['parsed']['live']]
    return max(v)
def target(lb, lvl):
    s, f = CFG[lb]; return 4 * s * MIB if lvl == 0 else (f ** lvl) * s * MIB
R = {lb: load(lb) for lb in CFG if os.path.isdir(os.path.join(D, lb))}
res = []
def chk(name, ok, detail): res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)
print('label  rows  stressErrors  peakL0(MiB)  L0target(MiB)  ratio  peakLive(MiB)  peakFileBytes(MiB)  settledFileBytes(MiB)  settledLive(MiB)  sstables(settled)  settled-drain-s')
for lb, o in R.items():
    pl = peak_l0(o); t0 = target(lb, 0) if CFG[lb] else 0
    print(f"{lb:6} {o['rows']} {o['errors']} {pl/MIB:9.1f} {t0/MIB:8.1f} {pl/t0 if t0 else 0:7.2f} {peak_live(o)/MIB:9.1f} {maxbytes(o)/MIB:9.1f} {o['settled-write']['bytes']/MIB:9.1f} {o['settled-write']['parsed']['live']/MIB:9.1f} {len(o['settled-write']['datafiles'])}")
chk('no write error in any run', all(o['errors'] == 0 for o in R.values()), str({k: o['errors'] for k, o in R.items()}))
chk('all runs wrote the same row count', len({o['rows'] for o in R.values()}) == 1, str({k: o['rows'] for k, o in R.items()}))
for lb in ('A', 'C'):
    if lb in R: chk(f'{lb}: peak L0 >= 10x its L0 target and >= 400 MiB', peak_l0(R[lb]) >= 10 * target(lb, 0) and peak_l0(R[lb]) >= 400 * MIB, f'{peak_l0(R[lb])/MIB:.0f} MiB vs {target(lb,0)/MIB:.0f}')
if 'B' in R: chk('B: peak L0 >= 1x its L0 target (640 MiB)', peak_l0(R['B']) >= target('B', 0), f"{peak_l0(R['B'])/MIB:.0f} MiB ({peak_l0(R['B'])/target('B',0):.2f}x)")
four = [k for k in ('A', 'B', 'C', 'D') if k in R]
pl = [peak_live(R[k]) for k in four]; st = [R[k]['settled-write']['bytes'] for k in four]
chk('peak total live bytes of A,B,C,D differ < 15%', max(pl) / min(pl) < 1.15, str({k: round(peak_live(R[k]) / MIB) for k in four}))
chk('settled file bytes of A,B,C,D differ < 15%', max(st) / min(st) < 1.15, str({k: round(R[k]['settled-write']['bytes'] / MIB) for k in four}))
if 'A' in R and 'C' in R: chk('C (fanout 2) settled bytes within 15% of A', abs(R['C']['settled-write']['bytes'] / R['A']['settled-write']['bytes'] - 1) < 0.15, f"{R['C']['settled-write']['bytes']/MIB:.0f} vs {R['A']['settled-write']['bytes']/MIB:.0f} MiB")
for lb in ('A', 'B', 'C', 'Aprime'):
    if lb not in R: continue
    if not R[lb]['settled-write']['parsed']['bytes']: continue
    lv = R[lb]['settled-write']['parsed']['bytes']; ratios = [lv[i] / target(lb, i) for i in range(len(lv))]
    top = max(i for i, x in enumerate(lv) if x)
    body = [ratios[i] for i in range(1, top)]
    print(f'INFO {lb} settled per-level bytes {lv} ratios-to-target {[round(r,3) for r in ratios]} top level L{top}')
    chk(f'{lb}: after drain L0 empty-ish and every level below the top <= 1.05 x target, total unchanged vs lag-end (<5%)', lv[0] <= target(lb, 0) and all(r <= 1.05 for r in body) and abs(R[lb]['settled-write']['parsed']['live'] / R[lb]['lag-end']['parsed']['live'] - 1) < 0.05, f"L0 {lv[0]/MIB:.0f} MiB; body ratios {[round(r,3) for r in body]}; live {R[lb]['settled-write']['parsed']['live']/MIB:.0f} vs {R[lb]['lag-end']['parsed']['live']/MIB:.0f} MiB")
if 'Aprime' in R and 'A' in R:
    # B3g control rows: a throughput/concurrency change moves the peak L0 (any reduction), levels settle at targets, total bytes unchanged
    chk("A' (fast compaction from the start): peak L0 below A's, settled bytes within 15% of A", peak_l0(R['Aprime']) < peak_l0(R['A']) and abs(R['Aprime']['settled-write']['bytes'] / R['A']['settled-write']['bytes'] - 1) < 0.15, f"peak L0 {peak_l0(R['Aprime'])/MIB:.0f} vs {peak_l0(R['A'])/MIB:.0f} MiB ({peak_l0(R['Aprime'])/peak_l0(R['A'])-1:+.1%})")
chk('every drain settled', all(json.load(open(f'{D}/{lb}/drain-write.json'))['settled'] for lb in R), 'ok')
chk('TRUNCATE control: file bytes after truncate < 1% of settled', all(o['truncated']['bytes'] < 0.01 * o['settled-write']['bytes'] for o in R.values()), str({k: o['truncated']['bytes'] for k, o in R.items()}))
print('ALL PASS' if all(res) else f'{res.count(False)} FAIL')
