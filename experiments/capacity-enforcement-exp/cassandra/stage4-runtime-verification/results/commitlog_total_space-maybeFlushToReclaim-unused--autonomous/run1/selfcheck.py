#!/usr/bin/env python3
"""Independent self-check for commitlog_total_space-maybeFlushToReclaim-unused--autonomous, run 1.
Usage: python3 selfcheck.py <run1 dir>
Does not use analyze.py, reasons.txt, counts.txt or flushes.txt. Re-reads the raw files:
 unit:    cap.csv (split by hand), every test log file (plain or .gz) for flush lines, ant.log (SUMMARY, Tests run),
          the TEST-*.xml (failures/errors attributes)
 cluster: du.csv, the node's full system.log and debug.log.gz (one node lifetime each), stress.out, times.txt, yaml.diff
Re-applies B2f/B2g and B3f/B3g (as amended R3) and prints 'ok'/'FAIL' per check and the matched row."""
import gzip, os, re, sys, datetime
R = sys.argv[1]; MiB = 1 << 20
res = []
def chk(name, cond, note=''):
    res.append(bool(cond)); print(f"{'ok  ' if cond else 'FAIL'} {name} {note}")

def read_any(p):
    with open(p, 'rb') as f: head = f.read(2)
    op = gzip.open if head == b'\x1f\x8b' else open
    with op(p, 'rt', errors='replace') as f: return f.read()

# ------------- unit
UNIT = {}
for arm, C, sl in [('cap15-s10', 15, 10), ('cap25-s10', 25, 10), ('cap50-s10', 50, 10), ('cap100000-s10', 100000, 10), ('cap25-s0', 25, 0)]:
    d = os.path.join(R, 'unit', arm)
    lines = open(os.path.join(d, 'cap.csv')).read().splitlines()
    hdr = lines[0].split(','); assert lines.count(lines[0]) == 1, 'one header (one JVM wrote this CSV)'
    ix = {h: i for i, h in enumerate(hdr)}
    data = [l.split(',') for l in lines[1:]]
    cap = {int(r[ix['capMiB']]) for r in data}
    od = [int(r[ix['onDiskSize']]) for r in data]; dirb = [int(r[ix['dirBytes']]) for r in data]
    sw = [int(r[ix['memtableSwitches']]) for r in data]
    writes = sum(1 for r in data if r[ix['phase']] == 'write'); settles = sum(1 for r in data if r[ix['phase']] == 'settle')
    logtxt = ''
    for root, _, fs in os.walk(os.path.join(d, 'testlogs')):
        for f in sorted(fs): logtxt += read_any(os.path.join(root, f))
    reasons = re.findall(r'Enqueuing flush of CLCapKS\.t, Reason: (\w+)', logtxt)
    cld = reasons.count('COMMITLOG_DIRTY'); ml = reasons.count('MEMTABLE_LIMIT'); other = len(reasons) - cld - ml
    ant = open(os.path.join(d, 'ant.log')).read()
    m = re.search(r'SUMMARY capMiB=(\d+) sleepMs=(\d+) n=(\d+) peakOnDisk=(\d+) peakDir=(\d+) final=(\d+) finalDir=(\d+) switches=(\d+)', ant)
    xml = open(os.path.join(d, 'TEST-org.apache.cassandra.db.commitlog.CommitLogTotalSpaceCapTest.xml')).read()
    xm = re.search(r'errors="(\d+)" failures="(\d+)"', xml) or re.search(r'failures="(\d+)".*?errors="(\d+)"', xml)
    info = re.search(r'INFO capMiB=(\d+) segMiB=(\d+) heapMaxMiB=(\d+) memtableHeapMiB=(\d+) cleanup=([\d.]+) accessMode=(\w+)', ant)
    u = dict(C=C, peak=max(od), peakDir=max(dirb), final=od[-1], sw=sw[-1], cld=cld, ml=ml, other=other,
             falls=sum(1 for a, b in zip(od, od[1:]) if a > b), od=od, dirb=dirb)
    UNIT[arm] = u
    chk(f"unit {arm} knob in force", cap == {C} and info and int(info.group(1)) == C, f"csv cap {cap}")
    chk(f"unit {arm} test env: 5 MiB mmap segments, memtable heap 768 MiB, cleanup 0.99", info and info.group(2) == '5' and info.group(4) == '768' and info.group(5) == '0.99' and info.group(6) == 'mmap', info.group(0) if info else '')
    chk(f"unit {arm} 300 writes + 10 settle rows", writes == 300 and settles == 10, f"{writes}+{settles}")
    chk(f"unit {arm} JUnit passed", xm and xm.group(1) == '0' and xm.group(2) == '0' and 'Tests run: 1, Failures: 0, Errors: 0' in ant)
    chk(f"unit {arm} SUMMARY agrees with the CSV", m and int(m.group(4)) == u['peak'] and int(m.group(5)) == u['peakDir'] and int(m.group(8)) == u['sw'],
        f"peak {u['peak']/MiB:.0f} MiB, dir {u['peakDir']/MiB:.0f}, sw {u['sw']}")
    chk(f"unit {arm} switch count = COMMITLOG_DIRTY + MEMTABLE_LIMIT + other flush lines of CLCapKS.t", u['sw'] == cld + ml + other, f"{u['sw']} vs {cld}+{ml}+{other}")
    print(f"     {arm}: peak {u['peak']/MiB:.0f} MiB, peakDir {u['peakDir']/MiB:.0f}, final {u['final']/MiB:.0f}, switches {u['sw']}, COMMITLOG_DIRTY {cld}, MEMTABLE_LIMIT {ml}, falls {u['falls']}")

S = 5 * MiB; ctl = UNIT['cap100000-s10']
chk("unit control: valid (>3x largest C, 0 flushes of any reason, monotone)", ctl['peak'] > 3 * 50 * MiB and ctl['sw'] == 0 and ctl['cld'] + ctl['ml'] + ctl['other'] == 0 and ctl['od'] == sorted(ctl['od']), f"{ctl['peak']/MiB:.0f} MiB")
chk("unit control within B2f (375-400 MiB)", 375 * MiB <= ctl['peak'] <= 400 * MiB)
for arm, bound, fin, swm in [('cap15-s10', 35, 20, 15), ('cap25-s10', 45, 30, 10), ('cap50-s10', 70, 55, 5)]:
    u = UNIT[arm]
    chk(f"unit {arm} R3(b) COMMITLOG_DIRTY>0 and (c) falls>0", u['cld'] > 0 and u['falls'] > 0)
    chk(f"unit {arm} not Refuted: peak and dirBytes peak < 0.8 x control", u['peak'] < 0.8 * ctl['peak'] and u['peakDir'] < 0.8 * ctl['peakDir'])
    chk(f"unit {arm} B2f peak <= {bound} MiB (sub-prediction)", u['peak'] <= bound * MiB, f"{u['peak']/MiB:.0f}")
    chk(f"unit {arm} B2f final <= {fin} MiB and switches >= {swm}", u['final'] <= fin * MiB and u['sw'] >= swm)
    chk(f"unit {arm} final >= floor 2S", u['final'] >= 2 * S)
p = UNIT['cap25-s0']
chk("unit probe 45 < peak < 150 MiB, final <= 30, switches >= 5", 45 * MiB < p['peak'] < 150 * MiB and p['final'] <= 30 * MiB and p['sw'] >= 5, f"{p['peak']/MiB:.0f}")
chk("unit probe < 0.8 x control (no bypass row)", p['peak'] < 0.8 * ctl['peak'])
chk("unit all onDiskSize multiples of S, |dir - counter| <= S", all(x % S == 0 for u in UNIT.values() for x in u['od']) and all(abs(a - b) <= S for u in UNIT.values() for a, b in zip(u['od'], u['dirb'])))
chk("unit monotone in C (peak up, switches down)", UNIT['cap15-s10']['peak'] < UNIT['cap25-s10']['peak'] < UNIT['cap50-s10']['peak'] and UNIT['cap15-s10']['sw'] > UNIT['cap25-s10']['sw'] > UNIT['cap50-s10']['sw'])
umiss = [a for a, b in [('cap15-s10', 35), ('cap25-s10', 45), ('cap50-s10', 70)] if UNIT[a]['peak'] > b * MiB]
print(f"UNIT ROW: {'row 1 (Confirmed - caps, soft)' if not umiss else 'row 4 (Confirmed - caps, soft; overshoot bound missed in ' + ','.join(umiss) + ')'}")

# ------------- cluster
S = 32 * MiB; CL = {}
def utc_ms(s):
    return int(datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
for arm, C, thr in [('256', 256, 1), ('1024', 1024, 1), ('16384', 16384, 1), ('256p', 256, 0)]:
    d = os.path.join(R, 'cluster', arm)
    t = {k: int(v) for k, v in (kv.split('=') for kv in open(os.path.join(d, 'times.txt')).read().split())}
    rows = []
    for l in open(os.path.join(d, 'du.csv')):
        f = l.strip().split(',')
        if len(f) == 5 and all(x.isdigit() for x in f): rows.append([int(x) for x in f])
    sysl = read_any(os.path.join(d, 'system.log'))
    fl = [(utc_ms(a), r) for a, r in re.findall(r'(\d{4}-\d\d-\d\dT[\d:,]+) ColumnFamilyStore\.java:\d+ - Enqueuing flush of keyspace1\.standard1, Reason: (\w+)', sysl)]
    fl_in = [(x, r) for x, r in fl if x <= t['TS']]
    cld = [x for x, r in fl_in if r == 'COMMITLOG_DIRTY']; ml = [x for x, r in fl_in if r == 'MEMTABLE_LIMIT']
    cfg = re.search(r'commitlog_total_space=([^;]+);', sysl)
    dbg = read_any(os.path.join(d, 'debug.log.gz'))
    deleted = [utc_ms(a) for a in re.findall(r'(\d{4}-\d\d-\d\dT[\d:,]+) AbstractCommitLogSegmentManager\.java:\d+ - Segment .* is no longer active and will be deleted now', dbg)]
    deleted = [y for y in deleted if y <= t['TS']]   # this lifetime up to settle end (shutdown deletions excluded)
    neq = sum(1 for r in rows if r[1] - 4096 != S * r[3])   # du -sb vs 32 MiB x ls count (sampled a moment apart)
    maxdev = max(abs(r[1] - 4096 - S * r[3]) for r in rows)
    st = open(os.path.join(d, 'stress.out')).read()
    parts = re.search(r'Total partitions\s*:\s*([\d,]+)', st); errs = re.search(r'Total errors\s*:\s*([\d,]+)', st)
    b = [r[1] for r in rows]
    # each standard1 COMMITLOG_DIRTY flush is followed within 60 s by segment deletions and a fall of the du trace
    followed = sum(1 for x in cld if any(x <= y <= x + 60000 for y in deleted) and
                   any(rows[i][0] >= x and rows[i][0] <= x + 60000 and rows[i + 1][1] < rows[i][1] for i in range(len(rows) - 1)))
    c = dict(C=C, peak=max(b), settle=b[-1], cld=len(cld), ml=len(ml), deleted=len(deleted), followed=followed,
             falls=sum(1 for i in range(len(b) - 1) if b[i] - b[i + 1] >= S), gap=max(r[0] for r in rows) - min(r[0] for r in rows),
             maxstep=max(rows[i + 1][0] - rows[i][0] for i in range(len(rows) - 1)), parts=parts and parts.group(1), errs=errs and errs.group(1),
             t=t, peak_t=rows[b.index(max(b))][0])
    CL[arm] = c
    chk(f"cluster {arm} du -sb ~ 32 MiB x file count (within 1 segment)", maxdev <= S, f"{neq}/{len(rows)} samples differ, max {maxdev/MiB:.0f} MiB")
    chk(f"cluster {arm} knob in force (startup config line)", cfg and cfg.group(1) == f"{C}MiB", cfg.group(1) if cfg else '')
    chk(f"cluster {arm} 3,000,000 partitions written, 0 errors", c['parts'] == '3,000,000' and c['errs'] == '0', f"{c['parts']} / {c['errs']}")
    chk(f"cluster {arm} sampler covers start to settle end, max gap <= 5 s", rows[0][0] <= t['T0'] + 2000 and rows[-1][0] >= t['TS'] - 3000 and c['maxstep'] <= 5000, f"{len(rows)} samples, max step {c['maxstep']} ms")
    print(f"     {arm}: peak {c['peak']/MiB:.1f} MiB at +{(c['peak_t']-t['T0'])/1000:.0f} s, settle {c['settle']/MiB:.1f}, standard1 COMMITLOG_DIRTY {c['cld']} (followed by deletion and fall: {followed}), MEMTABLE_LIMIT {c['ml']}, segments deleted {c['deleted']}, falls >= 1 seg {c['falls']}, stress {(t['T1']-t['T0'])/1000:.0f} s")
ctl = CL['16384']
chk("cluster control valid: peak >= 2.8 GiB (> 1.5 GiB), 0 MEMTABLE_LIMIT, 0 COMMITLOG_DIRTY", ctl['peak'] >= 2.8 * 1024 * MiB and ctl['ml'] == 0 and ctl['cld'] == 0, f"{ctl['peak']/MiB:.0f} MiB")
chk("cluster control settle ~ peak", ctl['settle'] >= 0.95 * ctl['peak'])
for arm, bound, sb, cm in [('256', 384, 288, 8), ('1024', 1152, 1056, 2)]:
    c = CL[arm]
    chk(f"cluster {arm} R3(b) COMMITLOG_DIRTY >= 1 and (c) falls > 0", c['cld'] >= 1 and c['falls'] > 0)
    chk(f"cluster {arm} not Refuted: peak < 0.8 x control", c['peak'] < 0.8 * ctl['peak'], f"{c['peak']/ctl['peak']:.3f}")
    chk(f"cluster {arm} MEMTABLE_LIMIT = 0", c['ml'] == 0)
    chk(f"cluster {arm} every COMMITLOG_DIRTY flush followed by deletion and a fall", c['followed'] == c['cld'], f"{c['followed']}/{c['cld']}")
    chk(f"cluster {arm} B3f peak <= {bound} MiB (sub-prediction)", c['peak'] <= bound * MiB, f"{c['peak']/MiB:.1f}")
    chk(f"cluster {arm} B3f settle <= {sb} MiB (sub-prediction)", c['settle'] <= sb * MiB, f"{c['settle']/MiB:.1f}")
    chk(f"cluster {arm} B3f COMMITLOG_DIRTY >= {cm} (sub-prediction)", c['cld'] >= cm, c['cld'])
p = CL['256p']
chk("cluster probe: COMMITLOG_DIRTY >= 8, MEMTABLE_LIMIT = 0", p['cld'] >= 8 and p['ml'] == 0, f"{p['cld']}/{p['ml']}")
chk("cluster probe peak < 1024 MiB and settle <= 288 MiB (sub-prediction)", p['peak'] < 1024 * MiB and p['settle'] <= 288 * MiB, f"{p['peak']/MiB:.1f}/{p['settle']/MiB:.1f}")
chk("cluster probe < 0.8 x control (no bypass row)", p['peak'] < 0.8 * ctl['peak'], f"{p['peak']/ctl['peak']:.3f}")
chk("cluster peak order 256 < 1024 < control", CL['256']['peak'] < CL['1024']['peak'] < ctl['peak'])
miss = [a for a, bd, sb in [('256', 384, 288), ('1024', 1152, 1056)] if CL[a]['peak'] > bd * MiB or CL[a]['settle'] > sb * MiB]
refuted = any(CL[a]['peak'] >= 0.8 * ctl['peak'] for a in ('256', '1024'))
noflush = any(CL[a]['cld'] == 0 for a in ('256', '1024'))
print("CLUSTER ROW:", 'Refuted (row 2)' if refuted else 'Not confirmed (no COMMITLOG_DIRTY)' if noflush else
      ('row 1 (Confirmed - caps, soft)' if not miss else 'row 4 (Confirmed - caps, soft; bound missed in ' + ','.join(miss) + ')') +
      ('; probe >= 0.8 x control: bypass' if p['peak'] >= 0.8 * ctl['peak'] else ''))
print(f"SELFCHECK {sum(res)} ok, {len(res) - sum(res)} FAIL")
