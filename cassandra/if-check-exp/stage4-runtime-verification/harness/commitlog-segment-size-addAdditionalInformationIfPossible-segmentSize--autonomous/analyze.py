#!/usr/bin/env python3
"""Summarise one cluster arm directory (cluster-run.sh output) and print EXPECTED lines (the B3f predictions).
Usage: analyze.py <arm-dir>. Prints SUMMARY/EXPECTED lines; exit 1 if an EXPECTED line failed."""
import re, sys, os, time, calendar, collections
d = sys.argv[1]
t = dict(kv.split('=') for kv in open(f'{d}/times.txt').read().split())
tot = int(t.get('TOT', '64')) * 1048576
arm = t['ARM']; seg = int(t['SEG']) * 1048576; vol = int(t['VOL']) * 1048576; free = int(t['FREE'])
NEEDLE = re.compile(r'(\d+) bytes required for next commitlog segment but only (\d+) bytes available')
ERRRE = re.compile(r'Failed to persist commits to disk|Failed managing commit log segments')
rows = []  # df samples: epoch_ms, apparent, nfiles, used, avail
for l in open(f'{d}/du.csv'):
    p = l.strip().split(',')
    if len(p) == 5 and all(x.lstrip('-').isdigit() for x in p):
        rows.append(tuple(int(x) for x in p))
def df_at(ms):
    best = None
    for r in rows:
        if r[0] <= ms: best = r
        else: break
    return best
errs = []; needles = []; other = collections.Counter()
for l in open(f'{d}/system.log.run', errors='replace'):
    m = re.match(r'^(ERROR|WARN)\s+\[[^\]]*\]\s+(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3})\s+(.*)', l)
    if not m: continue
    if m.group(1) == 'ERROR': other[m.group(4)[:90]] += 1
    ms = int(calendar.timegm(time.strptime(m.group(2), '%Y-%m-%dT%H:%M:%S')) * 1000)  # system.log is UTC + int(m.group(3))
    if ERRRE.search(l):
        errs.append((ms, m.group(4)))
        n = NEEDLE.search(l)
        if n: needles.append((ms, int(n.group(1)), int(n.group(2))))
print(f'SUMMARY arm={arm} vol={vol} seg={seg} free_after_filler={free}')
print(f'SUMMARY handleCommitError lines={len(errs)} with_needle={len(needles)}')
kinds = collections.Counter('persist' if 'persist' in e[1] else 'manage' for e in errs)
print(f'SUMMARY kinds={dict(kinds)}')
for ms, req, only in needles[:3]:
    r = df_at(ms)
    print(f'SUMMARY needle required={req} only={only} df_avail_then={r[4] if r else None} df_size={vol}')
if errs:
    r = df_at(errs[0][0]); print(f'SUMMARY first_error df_avail_then={r[4] if r else None} df_used={r[3] if r else None}')
for k, v in other.most_common(5): print(f'SUMMARY other_error {v}x {k}')
ap = [r[1] for r in rows if t['T0'] and r[0] >= int(t['T0'])]
used = [r[3] for r in rows if r[0] >= int(t['T0'])]
print(f'SUMMARY apparent_commitlog_bytes max={max(ap) if ap else None} df_used max={max(used) if used else None}')
jm = []
if os.path.exists(f'{d}/jmx.csv'):
    for l in open(f'{d}/jmx.csv'):
        p = l.strip().split(',')
        if len(p) == 2 and p[1].strip().isdigit(): jm.append((int(p[0]), int(p[1])))
if jm:
    print(f'SUMMARY TotalCommitLogSize samples={len(jm)} max={max(v for _, v in jm)}')
dead = os.path.getsize(f'{d}/hs_err.txt') > 0
print(f'SUMMARY hs_err_files={"yes" if dead else "no"}')
rc = 0
def exp(ok, msg):
    global rc
    print(('EXPECTED ok: ' if ok else 'EXPECTED MISSING: ') + msg)
    if not ok: rc = 1
if arm in ('A1', 'A2', 'A5', 'A5L'):
    exp(len(errs) >= 1, f'{arm}: a handleCommitError line is logged once free space is exhausted (lines={len(errs)})')
    exp(len(needles) == 0, f'{arm}: no "bytes required" text although df avail < segment (total {vol} >= segment {seg}) (needle lines={len(needles)})')
elif arm in ('A3', 'A4'):
    exp(len(errs) >= 1, f'{arm}: a handleCommitError line is logged (lines={len(errs)})')
    exp(len(needles) >= 1 and all(o == vol for _, _, o in needles), f'{arm}: "bytes required" text present with only == volume total {vol} (needles={[o for _,_,o in needles][:3]})')
elif arm == 'ZH':
    mx = max([v for _, v in jm] + [0])
    exp(len(errs) == 0 and len(needles) == 0, f'{arm}: roomy volume, no handleCommitError line and no text (lines={len(errs)})')
    exp(64 * 1048576 + seg < mx <= tot + seg, f'{arm}: TotalCommitLogSize max follows the larger commitlog_total_space: {64*1048576+seg} < max <= {tot+seg}, max={mx}')
else:
    mx = max([v for _, v in jm] + [0])
    exp(len(errs) == 0 and len(needles) == 0, f'{arm}: roomy volume, no handleCommitError line and no text (lines={len(errs)})')
    exp(0 < mx <= 64 * 1048576 + seg, f'{arm}: TotalCommitLogSize max <= commitlog_total_space + one segment ({64*1048576 + seg}), max={mx}')
sys.exit(rc)
