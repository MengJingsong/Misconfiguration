#!/usr/bin/env python3
"""Run-1 analysis for commitlog_total_space-maybeFlushToReclaim-unused--autonomous.
Usage: python3 analyze.py <run1 dir with unit/ and cluster/>
Reads the unit CSVs + reasons.txt and the cluster du.csv / jmx.csv / flushes.txt / counts.txt / times.txt,
prints the readings and one EXPECTED line per B2f/B3f prediction (yes/no). Logs a mismatch and goes on."""
import csv, os, re, sys, datetime
R = sys.argv[1]; MiB = 1 << 20
ok = fail = 0
def exp(name, cond, detail):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(f"EXPECTED: {name}: {'yes' if cond else 'NO'} ({detail})")

# ---------------- unit
S = 5 * MiB
U = os.path.join(R, 'unit'); unit = {}
for arm in ['cap15-s10', 'cap25-s10', 'cap50-s10', 'cap100000-s10', 'cap25-s0']:
    d = os.path.join(U, arm)
    if not os.path.isdir(d): print('missing', d); continue
    rows = list(csv.DictReader(open(os.path.join(d, 'cap.csv'))))
    rs = dict(l.split()[:2] for l in open(os.path.join(d, 'reasons.txt')) if not l.startswith('REASON'))
    od = [int(r['onDiskSize']) for r in rows]; db = [int(r['dirBytes']) for r in rows]
    sw = [int(r['memtableSwitches']) for r in rows]
    drops = sum(1 for a, b in zip(od, od[1:]) if b < a)
    unit[arm] = dict(peak=max(od), peakDir=max(db), final=od[-1], finalDir=db[-1], sw=sw[-1], drops=drops,
                     cld=int(rs['COMMITLOG_DIRTY']), ml=int(rs['MEMTABLE_LIMIT']), n=len(rows),
                     mult=all(x % S == 0 for x in od), within=max(abs(a - b) for a, b in zip(od, db)),
                     mono=all(b >= a for a, b in zip(od, od[1:])))
    u = unit[arm]
    print(f"UNIT {arm}: rows={u['n']} peak={u['peak']/MiB:.0f}MiB peakDir={u['peakDir']/MiB:.0f} final={u['final']/MiB:.0f} "
          f"finalDir={u['finalDir']/MiB:.0f} switches={u['sw']} COMMITLOG_DIRTY={u['cld']} MEMTABLE_LIMIT={u['ml']} drops={u['drops']} "
          f"multipleOfS={u['mult']} max|dir-counter|={u['within']/MiB:.2f}MiB monotone={u['mono']}")
if len(unit) == 5:
    ctl = unit['cap100000-s10']
    for arm, C, pk, fin, swmin in [('cap15-s10', 15, 35, 20, 15), ('cap25-s10', 25, 45, 30, 10), ('cap50-s10', 50, 70, 55, 5)]:
        u = unit[arm]
        exp(f"unit {arm} peak <= {pk} MiB", u['peak'] <= pk * MiB, f"{u['peak']/MiB:.0f}")
        exp(f"unit {arm} final <= {fin} MiB", u['final'] <= fin * MiB, f"{u['final']/MiB:.0f}")
        exp(f"unit {arm} switches >= {swmin}", u['sw'] >= swmin, u['sw'])
        exp(f"unit {arm} COMMITLOG_DIRTY > 0, MEMTABLE_LIMIT = 0", u['cld'] > 0 and u['ml'] == 0, f"{u['cld']}/{u['ml']}")
        exp(f"unit {arm} trace drops (sawtooth)", u['drops'] > 0, u['drops'])
        exp(f"unit {arm} peak < 0.8 x control (not Refuted)", u['peak'] < 0.8 * ctl['peak'], f"{u['peak']/ctl['peak']:.3f}")
        exp(f"unit {arm} dirBytes peak < 0.8 x control dirBytes (not counter-only)", u['peakDir'] < 0.8 * ctl['peakDir'], f"{u['peakDir']/ctl['peakDir']:.3f}")
    exp("unit control peak 375-400 MiB, monotone", 375 * MiB <= ctl['peak'] <= 400 * MiB and ctl['mono'], f"{ctl['peak']/MiB:.0f}, {ctl['mono']}")
    exp("unit control switches = 0, COMMITLOG_DIRTY = 0, MEMTABLE_LIMIT = 0", ctl['sw'] == 0 and ctl['cld'] == 0 and ctl['ml'] == 0, f"{ctl['sw']}/{ctl['cld']}/{ctl['ml']}")
    exp("unit control final = peak", ctl['final'] == ctl['peak'], f"{ctl['final']/MiB:.0f}")
    exp("unit control > 3 x largest C (150 MiB)", ctl['peak'] > 150 * MiB, f"{ctl['peak']/MiB:.0f}")
    p = unit['cap25-s0']
    exp("unit probe 25:0 45 < peak < 150 MiB", 45 * MiB < p['peak'] < 150 * MiB, f"{p['peak']/MiB:.0f}")
    exp("unit probe final <= 30 MiB", p['final'] <= 30 * MiB, f"{p['final']/MiB:.0f}")
    exp("unit probe switches >= 5", p['sw'] >= 5, p['sw'])
    exp("unit probe peak < 0.8 x control (no bypass)", p['peak'] < 0.8 * ctl['peak'], f"{p['peak']/ctl['peak']:.3f}")
    exp("unit onDiskSize always a multiple of 5 MiB", all(u['mult'] for u in unit.values()), '')
    exp("unit |dirBytes - onDiskSize| <= 1 segment", all(u['within'] <= S for u in unit.values()), f"max {max(u['within'] for u in unit.values())/MiB:.2f} MiB")
    pk = [unit[a]['peak'] for a in ('cap15-s10', 'cap25-s10', 'cap50-s10')]
    sws = [unit[a]['sw'] for a in ('cap15-s10', 'cap25-s10', 'cap50-s10')]
    exp("unit peak rises with C", pk[0] < pk[1] < pk[2] < ctl['peak'], [x // MiB for x in pk])
    exp("unit switches fall with C", sws[0] > sws[1] > sws[2] >= ctl['sw'], sws)

# ---------------- cluster
S = 32 * MiB
C = os.path.join(R, 'cluster'); cl = {}
ts_re = re.compile(r'^\w+\s+\[[^\]]+\] (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d,\d{3}) .*Enqueuing flush of keyspace1\.standard1, Reason: (\w+)')
def ms(s):
    return int(datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
for arm in ['256', '1024', '16384', '256p']:
    d = os.path.join(C, arm)
    if not os.path.isfile(os.path.join(d, 'DONE')): print('missing/unfinished', d); continue
    t = dict(kv.split('=') for kv in open(os.path.join(d, 'times.txt')).read().split())
    T0, T1, TS = int(t['T0']), int(t['T1']), int(t['TS'])
    rows = [list(map(int, l.strip().split(','))) for l in open(os.path.join(d, 'du.csv')) if l.strip().count(',') == 4]
    b = [r[1] for r in rows]; files = [r[3] for r in rows]
    cnt = dict(l.split()[:2] for l in open(os.path.join(d, 'counts.txt')) if not l.startswith('REASON'))
    fl = [(ms(m.group(1)), m.group(2)) for m in (ts_re.match(l) for l in open(os.path.join(d, 'flushes.txt'))) if m]
    cld_t = [x for x, r in fl if r == 'COMMITLOG_DIRTY']
    drops = [(rows[i + 1][0], rows[i][1] - rows[i + 1][1]) for i in range(len(rows) - 1) if rows[i][1] - rows[i + 1][1] >= S]
    aligned = sum(1 for tt, _ in drops if any(0 <= tt - x <= 60000 for x in cld_t))
    eq = max(abs(r[1] - 4096 - S * r[3]) for r in rows)
    stress = open(os.path.join(d, 'stress.out')).read()
    tp = re.search(r'Total partitions\s*:\s*([\d,]+)', stress); te = re.search(r'Total errors\s*:\s*([\d,]+)', stress)
    rate = re.search(r'Op rate\s*:\s*([\d,]+)', stress)
    jm = [l.strip().split(',') for l in open(os.path.join(d, 'jmx.csv')) if re.match(r'^\d+,\d+$', l.strip())]
    cl[arm] = dict(peak=max(b), settle=b[-1], files_peak=max(files), cld=int(cnt['COMMITLOG_DIRTY_standard1']),
                   ml=int(cnt['MEMTABLE_LIMIT_standard1']), drops=len(drops), aligned=aligned, eq=eq,
                   parts=tp.group(1) if tp else '?', errs=te.group(1) if te else '?', rate=rate.group(1) if rate else '?',
                   dur=(T1 - T0) / 1000, jpeak=max([int(v) for _, v in jm], default=-1), nj=len(jm),
                   data=rows[-1][4], ns=len(rows))
    c = cl[arm]
    print(f"CLUSTER {arm}: samples={c['ns']} peak={c['peak']/MiB:.1f}MiB settle={c['settle']/MiB:.1f}MiB maxFiles={c['files_peak']} "
          f"COMMITLOG_DIRTY={c['cld']} MEMTABLE_LIMIT={c['ml']} drops>=1seg={c['drops']} aligned={c['aligned']} "
          f"max|du-4096-32MiB*files|={c['eq']} partitions={c['parts']} errors={c['errs']} oprate={c['rate']} stress={c['dur']:.0f}s "
          f"jmxPeak={c['jpeak']/MiB:.0f}MiB({c['nj']} samples) dataDirEnd={c['data']/MiB:.0f}MiB")
if len(cl) == 4:
    ctl = cl['16384']
    for arm, Cm, pk, st, cmin in [('256', 256, 384, 288, 8), ('1024', 1024, 1152, 1056, 2)]:
        c = cl[arm]
        exp(f"cluster {arm} peak <= {pk} MiB", c['peak'] <= pk * MiB, f"{c['peak']/MiB:.1f}")
        exp(f"cluster {arm} settle <= {st} MiB", c['settle'] <= st * MiB, f"{c['settle']/MiB:.1f}")
        exp(f"cluster {arm} COMMITLOG_DIRTY >= {cmin}", c['cld'] >= cmin, c['cld'])
        exp(f"cluster {arm} MEMTABLE_LIMIT = 0", c['ml'] == 0, c['ml'])
        exp(f"cluster {arm} drops aligned with COMMITLOG_DIRTY", c['drops'] > 0 and c['aligned'] == c['drops'], f"{c['aligned']}/{c['drops']}")
        exp(f"cluster {arm} peak < 0.8 x control", c['peak'] < 0.8 * ctl['peak'], f"{c['peak']/ctl['peak']:.3f}")
    exp("cluster control peak >= 2.8 GiB", ctl['peak'] >= 2.8 * 1024 * MiB, f"{ctl['peak']/MiB:.0f} MiB")
    exp("cluster control COMMITLOG_DIRTY = 0, MEMTABLE_LIMIT = 0", ctl['cld'] == 0 and ctl['ml'] == 0, f"{ctl['cld']}/{ctl['ml']}")
    exp("cluster control settle ~ peak (>= 0.95)", ctl['settle'] >= 0.95 * ctl['peak'], f"{ctl['settle']/ctl['peak']:.3f}")
    p = cl['256p']
    exp("cluster probe 256p peak < 1024 MiB", p['peak'] < 1024 * MiB, f"{p['peak']/MiB:.1f}")
    exp("cluster probe 256p settle <= 288 MiB", p['settle'] <= 288 * MiB, f"{p['settle']/MiB:.1f}")
    exp("cluster probe 256p COMMITLOG_DIRTY >= 8, MEMTABLE_LIMIT = 0", p['cld'] >= 8 and p['ml'] == 0, f"{p['cld']}/{p['ml']}")
    exp("cluster probe peak < 0.8 x control (no bypass)", p['peak'] < 0.8 * ctl['peak'], f"{p['peak']/ctl['peak']:.3f}")
    exp("cluster peak order 256 < 1024 < control", cl['256']['peak'] < cl['1024']['peak'] < ctl['peak'], '')
    exp("cluster du -sb = 32 MiB x files (+4096 dir entry)", all(c['eq'] == 0 for c in cl.values()), [c['eq'] for c in cl.values()])
    exp("cluster all writes ok (3,000,000 partitions, 0 errors)", all(c['parts'] == '3,000,000' and c['errs'] == '0' for c in cl.values()), '')
print(f"TOTAL EXPECTED yes={ok} no={fail}")
