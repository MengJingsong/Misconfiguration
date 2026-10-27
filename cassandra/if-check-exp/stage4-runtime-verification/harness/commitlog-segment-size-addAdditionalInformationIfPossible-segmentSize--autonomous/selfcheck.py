#!/usr/bin/env python3
"""Independent self-check: re-derives every number the conclusion cites from the raw files, by a different code path than analyze.py
(grep subprocesses on the raw system.log from the recorded byte offset, plain split() parsing of df/JMX samples).
Usage: selfcheck.py <unit-outdir> <cluster-outroot>   (cluster-outroot holds <ARM>-r<rep> dirs). Prints CHECK lines; exit 1 on any NOT OK."""
import sys, os, re, subprocess, glob, gzip, calendar, time
bad = 0
def chk(ok, msg):
    global bad
    print(('CHECK ok: ' if ok else 'CHECK NOT OK: ') + msg)
    if not ok: bad += 1
def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True).stdout
u, root = sys.argv[1], sys.argv[2]
# ---- unit tier: the raw probe lines
P = open(f'{u}/probe.out').read().splitlines()
res = [l for l in P if l.startswith('RESULT ')]
chk(sum(l.startswith('RESULT FAIL') for l in res) == 0, f'unit: no FAIL line ({len(res)} RESULT lines)')
def kv(l, k):
    m = re.search(r'\b' + k + r'=(-?\d+)', l); return int(m.group(1)) if m else None
for l in res:
    if ' S1 ' in l or ' S5 ' in l: chk('aug=true' in l and kv(l, 'only') == 16777216 == kv(l, 'df_size'), 'unit: ' + l[:90])
    if ' S2 ' in l or ' S3 ' in l or ' S4 ' in l: chk('aug=false' in l and kv(l, 'operand') == kv(l, 'df_size'), 'unit: ' + l[:90])
full = [l for l in res if ' S4 ' in l]
chk(len(full) == 4 and all(kv(l, 'df_avail_after') <= 65536 and kv(l, 'operand') > 2**31 for l in full), 'unit: big volume had <= 64 KiB free while the operand was the 4 GiB total, all 4 segment sizes not augmented')
s6 = {kv(l, 'seg'): ('aug=true' in l) for l in res if ' S6 ' in l}
chk(s6 == {8: False, 16: False, 17: True, 1024: True}, f'unit: dose-response around the 16 MiB total with the volume full: {s6}')
c1 = [l for l in res if ' C1 ' in l]
chk(len(c1) == 3 and all(kv(l, 'length') == kv(l, 'expected') for l in c1), 'unit: segment file length = segment size (positive control)')
s8 = [l for l in res if ' S8 ' in l]
chk(len(s8) == 4, 'unit: handleCommitError lines for 2 policies x 2 volumes')
# ---- cluster tier
for d in sorted(glob.glob(f'{root}/*-r*')):
    arm = os.path.basename(d).split('-r')[0]
    if not os.path.exists(f'{d}/DONE'): chk(False, f'{arm}: DONE marker'); continue
    t = dict(kv_.split('=') for kv_ in open(f'{d}/times.txt').read().split())
    vol = int(t['VOL']) * 1048576; seg = int(t['SEG']) * 1048576
    off = int(open(f'{d}/system.log.offset').read())
    full_gz = f'{d}/system.log.full.gz'
    raw = gzip.open(full_gz).read()[off:].decode(errors='replace') if os.path.exists(full_gz) else open(f'{d}/system.log.full').read()
    lines = raw.splitlines()
    need = [l for l in lines if 'bytes required for next commitlog segment' in l]
    err = [l for l in lines if l.startswith('ERROR') and ('Failed to persist commits to disk' in l or 'Failed managing commit log segments' in l)]
    onlys = sorted(set(int(re.search(r'but only (\d+) bytes', l).group(1)) for l in need))
    reqs = sorted(set(int(re.search(r'(\d+) bytes required', l).group(1)) for l in need))
    print(f'INFO {arm}: error lines={len(err)} needle lines={len(need)} only-values={onlys} required-values={reqs}')
    # df at the first error line, from the raw sampler, independent of analyze.py
    if err:
        ts = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3})', err[0])
        ms = calendar.timegm(time.strptime(ts.group(1), '%Y-%m-%dT%H:%M:%S')) * 1000 + int(ts.group(2))
        prev = None
        for l in open(f'{d}/du.csv'):
            f = l.strip().split(',')
            if len(f) == 5 and f[0].isdigit() and int(f[0]) <= ms: prev = f
        print(f'INFO {arm}: df used/avail at the first error line: {prev[3:] if prev else None}')
    hs = os.path.exists(f'{d}/hs_err.txt') and os.path.getsize(f'{d}/hs_err.txt') > 0
    alive = [l for l in open(f'{d}/session.log') if 'daemon alive after settle' in l]
    print(f'INFO {arm}: hs_err={hs}; {alive[0].strip()[-40:] if alive else "no alive line"}')
    if arm in ('A1', 'A2', 'A5', 'A5L'):
        chk(len(need) == 0, f'{arm}: no "bytes required" text in the run window')
    if arm in ('A3', 'A4'):
        chk(len(need) >= 1 and onlys == [vol] and reqs == [seg], f'{arm}: text present, only == {vol}, required == {seg}')
    if arm in ('Z32', 'Z8', 'ZH'):
        vals = [int(l.split(',')[1]) for l in open(f'{d}/jmx.csv') if len(l.split(',')) == 2 and l.split(',')[1].strip().isdigit()]
        mx = max(vals) if vals else 0
        chk(len(err) == 0 and len(need) == 0 and 0 < mx <= int(t.get('TOT', '64')) * 1048576 + seg, f'{arm}: no error, no text, TotalCommitLogSize max {mx} <= {int(t.get("TOT", "64"))*1048576+seg} ({len(vals)} samples)')
        du = [int(l.split(',')[1]) for l in open(f'{d}/du.csv') if len(l.split(',')) == 5 and l.split(',')[0].isdigit() and int(l.split(',')[0]) >= int(t['T0'])]
        print(f'INFO {arm}: apparent commit-log bytes max={max(du)}')
sys.exit(1 if bad else 0)
