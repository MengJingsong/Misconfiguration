#!/usr/bin/env python3
"""Cluster tier analysis, sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous (B3f/B3g). usage: cluster-analyze.py <outdir with N5 N160 N1024 S160>"""
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
    return max([x['parsed']['bytes'][0] for x in o['samples'] if x.get('parsed') and x['parsed']['bytes']] + [o['lag-end']['parsed']['bytes'][0]])

D = sys.argv[1]
SIZE = {'N5': 5, 'N160': 160, 'N1024': 1024, 'S160': 160}
R = {lb: load(D, lb) for lb in SIZE if os.path.isdir(os.path.join(D, lb))}
res = []
def chk(name, ok, detail): res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)
print('label rows errors peakL0(MiB) L0target(MiB) peakFile(MiB) settledFile(MiB) settledLive(MiB) files median(MiB) max(MiB) drain-s')
for lb, o in R.items():
    df = o['settled-write']['datafiles']
    print(f"{lb:6} {o['rows']} {o['errors']} {peak_l0(o)/MIB:8.0f} {4*SIZE[lb]:6} {peak_file_bytes(o)/MIB:8.0f} {o['settled-write']['bytes']/MIB:8.0f} {o['settled-write']['parsed']['live']/MIB:8.0f} {len(df)} {statistics.median(df)/MIB:7.1f} {max(df)/MIB:7.1f} {o['drain']['seconds']}")
chk('no write error; same row count', all(o['errors'] == 0 for o in R.values()) and len({o['rows'] for o in R.values()}) == 1, str({k: (o['errors'], o['rows']) for k, o in R.items()}))
main = [k for k in ('N5', 'N160', 'N1024') if k in R]
lv = [R[k]['settled-write']['parsed']['live'] for k in main]; fb = [R[k]['settled-write']['bytes'] for k in main]
chk('settled live bytes within ~10% across N=5,160,1024', max(lv) / min(lv) < 1.10 and max(fb) / min(fb) < 1.10, str({k: round(R[k]['settled-write']['parsed']['live'] / MIB) for k in main}))
for k in ('N5', 'N160'):
    if k in R:
        df = R[k]['settled-write']['datafiles']; n = SIZE[k]
        chk(f'{k}: median file ~ N MiB (0.8N..1.2N) and no file above N MiB + 5%', 0.8 * n <= statistics.median(df) / MIB <= 1.2 * n and max(df) <= 1.05 * n * MIB, f'median {statistics.median(df)/MIB:.1f} max {max(df)/MIB:.1f}')
cnt = {k: len(R[k]['settled-write']['datafiles']) for k in main}
chk('file count falls as N rises (positive control: the file-size histogram follows N)', cnt.get('N5', 0) > cnt.get('N160', 0) > cnt.get('N1024', 0), str(cnt))
chk('peak file bytes exceed the settled bytes in every main run (transient compaction space)', all(peak_file_bytes(R[k]) > R[k]['settled-write']['bytes'] for k in main), str({k: (round(peak_file_bytes(R[k]) / MIB), round(R[k]['settled-write']['bytes'] / MIB)) for k in main}))
if 'N1024' in R:
    print(f"INFO N1024 limit check: peak L0 {peak_l0(R['N1024'])/MIB:.0f} MiB vs L0 target 4096 MiB -> limit {'reached' if peak_l0(R['N1024']) >= 4096 * MIB else 'NOT reached'}")
if 'S160' in R:
    o = R['S160']; chk('S160 (compaction 1 MiB/s): L0 bytes exceed 4 x 160 = 640 MiB with no write error', peak_l0(o) > 640 * MIB and o['errors'] == 0, f'peak L0 {peak_l0(o)/MIB:.0f} MiB')
    print('INFO S160 lag-end per-level bytes', o['lag-end']['parsed']['bytes'], 'count', o['lag-end']['parsed']['count'])
for k, o in R.items():
    print(f"INFO {k} settled per-level bytes {o['settled-write']['parsed']['bytes']} count {o['settled-write']['parsed']['count']}")
chk('every drain settled', all(o['drain']['settled'] for o in R.values()), str({k: o['drain']['seconds'] for k, o in R.items()}))
chk('TRUNCATE control: file bytes after truncate < 1% of settled', all(o['truncated']['bytes'] < 0.01 * o['settled-write']['bytes'] for o in R.values()), str({k: o['truncated']['bytes'] for k, o in R.items()}))
print('ALL PASS' if all(res) else f'{res.count(False)} FAIL')
