#!/usr/bin/env python3
"""Independent re-parse of run 1's raw files (not the harness summaries). usage: selfcheck.py <logs-dir>   (~/s4-b9-cs-logs/run1)
Cluster: per life, from system.log.lifeN: MEMTABLE_LIMIT flush lines per table (reason, off-heap usage), 'Completed flushing ... Data.db (X MiB)' sums,
         from session.log: the exact rejection messages and counts; from samples-*.csv: peak RssAnon, last table_dir_bytes and commit log max.
Unit: from the .out files: the grid MISMATCH count and the series/stream numbers."""
import glob, os, re, sys, collections
L = sys.argv[1]
print('== unit ==')
for f in sorted(glob.glob(L + '/unit/*.out')):
    t = open(f).read()
    print(os.path.basename(f), 'checks', len(re.findall(r'^STAGE4 check', t, re.M)), 'MISMATCH', t.count('MISMATCH'),
          ' | '.join(re.findall(r'STAGE4 (?:series S=\d+ cap=\d+ slope_bytes_per_key=[\d.]+ delta_first_to_last=-?\d+ delta_3_to_10=-?\d+ thrown=\d+|stream m=\d+ S=\d+ accepted=\d+ rejected=\d+ bytes_validated=\d+)', t)))
grid = open(L + '/unit/grid.out').read()
rej = [l for l in grid.splitlines() if l.startswith('STAGE4 cell') and 'rejected' in l]
acc = [l for l in grid.splitlines() if l.startswith('STAGE4 cell') and 'accepted' in l]
print('grid cells rejected', len(rej), 'accepted', len(acc))
for l in grid.splitlines():
    if l.startswith('STAGE4 cell') and ('32768' in l and 'mixed' in l or 'S=65535,N=2' in l or 'S=65536,N=1' in l): print('  ', l[:170])
print('== cluster ==')
FL = re.compile(r'Enqueuing flush of (ks\.\S+), Reason: (\w+), Usage: ([\d.]+)(KiB|MiB|GiB|B) \(\d+%\) on-heap, ([\d.]+)(KiB|MiB|GiB|B) \(\d+%\) off-heap')
CP = re.compile(r'Completed flushing \S*/ks/(t_[a-z0-9_]+)-\S*Data\.db \(([\d.]+)(KiB|MiB|GiB)\)')
U = {'B': 1 / 1048576, 'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024}
for life in (1, 2, 3):
    p = f'{L}/cluster/system.log.life{life}'
    if not os.path.exists(p): continue
    t = open(p).read(); per = collections.defaultdict(list); comp = collections.defaultdict(float)
    for m in FL.finditer(t): per[(m.group(1), m.group(2))].append((float(m.group(3)) * U[m.group(4)], float(m.group(5)) * U[m.group(6)]))
    for m in CP.finditer(t): comp[m.group(1)] += float(m.group(2)) * U[m.group(3)]
    print(f'-- life {life}: system.log lines {t.count(chr(10))}, ERROR lines {len(re.findall(r"^ERROR", t, re.M))}, AssertionError {t.count("AssertionError")}')
    for (tab, reason), v in sorted(per.items()):
        if reason in ('MEMTABLE_LIMIT', 'USER_FORCED'):
            print(f'   {tab} {reason}: n={len(v)} first off-heap {v[0][1]:.1f} MiB, max off-heap {max(x[1] for x in v):.1f} MiB')
    for tab, mib in sorted(comp.items()):
        print(f'   {tab}: sum of "Completed flushing" Data.db {mib:.0f} MiB')
s = open(L + '/cluster/session.log').read()
c = collections.Counter(re.findall(r'(Key length of \d+ is longer than maximum of 65535)', s))
print('rejection messages in session.log (each writer output repeats):', dict(c))
for f in sorted(glob.glob(L + '/cluster/samples-*.csv')):
    rows = [l.strip().split(',') for l in open(f).read().splitlines()[1:] if l.strip()]
    if rows:
        print(os.path.basename(f), 'n', len(rows), 'RssAnon max %.0f MiB min %.0f MiB' % (max(int(r[1]) for r in rows) / 1048576, min(int(r[1]) for r in rows) / 1048576),
              'table dir max %.0f MiB' % (max(int(r[2]) for r in rows) / 1048576), 'commitlog max %.0f MiB' % (max(int(r[3]) for r in rows) / 1048576))
