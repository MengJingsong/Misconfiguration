#!/usr/bin/env python3
"""Cluster tier analysis, sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous (B3f/B3g). usage: cluster-analyze.py <outdir with N5 N20 N160 T20 STCS>"""
import sys, json, os, re, statistics
MIB = 1048576
def load(D, lb, extra=()):
    d = os.path.join(D, lb); o = {'dir': d}
    for t in ('lag-end', 'settled-write', 'truncated') + tuple(extra): o[t] = json.load(open(f'{d}/snapshot-{t}.json'))
    o['samples'] = [json.loads(l) for l in open(f'{d}/samples-standard1.jsonl')]
    st = open(f'{d}/stress-write.txt').read()
    o['errors'] = int(re.search(r'Total errors\s*:\s*(\d+)', st).group(1))
    o['rows'] = int(re.search(r'Total partitions\s*:\s*([\d,]+)', st).group(1).replace(',', ''))
    o['drain'] = json.load(open(f'{d}/drain-write.json'))
    return o
def peak_file_bytes(o): return max(max([x['bytes'] for x in o['samples'] if 'bytes' in x] or [0]), o['lag-end']['bytes'])
def peak_l0(o):
    v = [x['parsed']['bytes'][0] for x in o['samples'] if x.get('parsed') and x['parsed']['bytes']]
    if o['lag-end']['parsed']['bytes']: v.append(o['lag-end']['parsed']['bytes'][0])
    return max(v) if v else 0
D = sys.argv[1]
SIZE = {'N5': 5, 'N20': 20, 'N160': 160, 'T20': 20, 'STCS': None}
R = {}
for lb in SIZE:
    if os.path.isdir(os.path.join(D, lb)):
        ex = ('lag-end-overwrite', 'settled-overwrite') + (('settled-big',) if SIZE[lb] else ())
        R[lb] = load(D, lb, ex)
res = []
def chk(name, ok, detail): res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)
print('label rows errors peakL0(MiB) peakFile(MiB) settledFile(MiB) settledLive(MiB) files median(MiB) max(MiB) bigMax(MiB) overwriteSettled(MiB)')
for lb, o in R.items():
    df = o['settled-write']['datafiles']; bg = o.get('settled-big')
    print(f"{lb:5} {o['rows']} {o['errors']} {peak_l0(o)/MIB:8.0f} {peak_file_bytes(o)/MIB:8.0f} {o['settled-write']['bytes']/MIB:8.0f} {o['settled-write']['parsed']['live']/MIB:8.0f} {len(df)} {statistics.median(df)/MIB:7.1f} {max(df)/MIB:7.1f} {(max(bg['datafiles'])/MIB if bg else 0):7.1f} {o['settled-overwrite']['bytes']/MIB:8.0f}")
chk('no write error; same row count', all(o['errors'] == 0 for o in R.values()) and len({o['rows'] for o in R.values()}) == 1, str({k: (o['errors'], o['rows']) for k, o in R.items()}))
main = [k for k in ('N5', 'N20', 'N160') if k in R]
lv = [R[k]['settled-write']['parsed']['live'] for k in main]; fb = [R[k]['settled-write']['bytes'] for k in main]
chk('settled live bytes differ < 10% across N=5,20,160', max(lv) / min(lv) < 1.10 and max(fb) / min(fb) < 1.10, str({k: round(R[k]['settled-write']['parsed']['live'] / MIB) for k in main}))
if 'STCS' in R: chk('STCS reference within 10% of the LCS runs', all(abs(R['STCS']['settled-write']['bytes'] / R[k]['settled-write']['bytes'] - 1) < 0.10 for k in main), f"{R['STCS']['settled-write']['bytes']/MIB:.0f} MiB")
cnt = {k: len(R[k]['settled-write']['datafiles']) for k in main}
chk('SSTable count falls as N rises (about 4x from 5 to 20; 8x or limited by data from 20 to 160)', cnt['N5'] > cnt['N20'] > cnt['N160'] and cnt['N5'] / cnt['N20'] > 2.5 and cnt['N20'] / cnt['N160'] > 3, f"{cnt}; ratios {cnt['N5']/cnt['N20']:.1f} and {cnt['N20']/cnt['N160']:.1f}")
for k in main:
    n = SIZE[k]; df = R[k]['settled-write']['datafiles']
    chk(f'{k}: regular-table max sstable ~ N MiB (<= N + 5%) and median >= 0.5 N', max(df) <= 1.05 * n * MIB and statistics.median(df) >= 0.5 * n * MIB, f'median {statistics.median(df)/MIB:.1f} max {max(df)/MIB:.1f}')
    bg = R[k].get('settled-big')
    PART = 40960000   # one large partition = 10,000 rows x 4096 B (amendment N6)
    if bg and PART > n * MIB: chk(f'{k}: large-partition table has an sstable above N MiB (partition {PART/MIB:.1f} MiB > N)', max(bg['datafiles']) > n * MIB, f"max {max(bg['datafiles'])/MIB:.1f} MiB vs N={n}")
    elif bg: print(f"INFO {k}: large-partition test NOT APPLICABLE: the partition ({PART/MIB:.1f} MiB) and even all three ({3*PART/MIB:.1f} MiB) are smaller than N={n} MiB; largest file {max(bg['datafiles'])/MIB:.1f} MiB (limit never reached for this arm)")
chk('peak file bytes exceed settled bytes in every main run', all(peak_file_bytes(R[k]) > R[k]['settled-write']['bytes'] for k in main), str({k: (round(peak_file_bytes(R[k]) / MIB), round(R[k]['settled-write']['bytes'] / MIB)) for k in main}))
def ratios(o, n, until=None):
    """max over the 20-s samples (optionally only those taken before `until`) of level bytes / (4N or 10^level x N)"""
    mx = {}
    for x in o['samples']:
        if x.get('parsed') and x['parsed']['bytes'] and (until is None or x['t'] <= until):
            for i, b in enumerate(x['parsed']['bytes']):
                mx[i] = max(mx.get(i, 0), b / ((4 if i == 0 else 10 ** i) * n * MIB))
    return {i: round(v, 2) for i, v in mx.items() if v}
if 'T20' in R:
    o = R['T20']; tw = o['lag-end']['t'] + 1
    rw = ratios(o, 20, tw); ra = ratios(o, 20)
    print('INFO T20 level-to-quota ratios, max over samples before the end of the throttled write:', rw, '| over the whole run (includes the unthrottled overwrite phase):', ra)
    chk('T20 (16 MiB/s write phase): L0 exceeds its 4N quota', rw.get(0, 0) > 1.001, f'L0 {rw.get(0)}x')
    chk('T20 (16 MiB/s write phase): a level above L0 exceeds fanout^level x N (B3f bullet 4)', any(r > 1.001 for i, r in rw.items() if i >= 1), f'ratios {rw}')
for k, o in R.items():
    print(f"INFO {k} settled per-level bytes {o['settled-write']['parsed']['bytes']}; after overwrite: file bytes {o['settled-overwrite']['bytes']/MIB:.0f} MiB (write phase {o['settled-write']['bytes']/MIB:.0f})")
chk('every drain settled', all(o['drain']['settled'] for o in R.values()), str({k: o['drain']['seconds'] for k, o in R.items()}))
chk('TRUNCATE control: file bytes after truncate < 1% of settled', all(o['truncated']['bytes'] < 0.01 * o['settled-write']['bytes'] for o in R.values()), str({k: o['truncated']['bytes'] for k, o in R.items()}))
print('ALL PASS' if all(res) else f'{res.count(False)} FAIL')
