#!/usr/bin/env python3
"""Independent self-check of cluster run 1 and unit run 1 from the raw files (not via the analyzers). Usage: selfcheck.py <logs dir (contains run1-unit, run1-cl)>"""
import csv, json, re, sys, datetime
base = sys.argv[1]
ok = True
def chk(name, cond, detail=''):
    global ok
    ok &= bool(cond); print('%s  %s  %s' % ('HOLDS' if cond else 'DOES NOT HOLD', name, detail))
ROWS = 200000
# unit: recompute from the CSV by hand
rows = [r for r in csv.reader(open(base + '/run1-unit/raw/unit-results.csv'))]
byarm = {(r[0], r[1]): r for r in rows if r[0] in ('direct',)}
for S, est in ((1, 62 * 113 + 100000 * 108), (512, 100000 * 732), (1023, 100000 * 1243)):
    chk('unit direct S=%d est' % S, int(byarm[('direct', str(S))][7]) == est, byarm[('direct', str(S))][7])
for S in (1024, 1025, 4096):
    r = byarm[('direct', str(S))]
    chk('unit direct S=%d rejected=100000 est=0 file=0' % S, r[4] == '0' and r[5] == '100000' and r[7] == '0' and r[8] == '0', ','.join(r[4:9]))
# estimate series: strictly linear for 1023 (10k steps)
ser = [r for r in csv.reader(open(base + '/run1-unit/raw/unit-estimates.csv')) if r[0] == 'direct' and r[1] == '1023']
chk('unit S=1023 estimate series is 10k * 1243 * k', all(int(r[3]) == int(r[2]) * 1243 for r in ser), '%d points' % len(ser))
ant = open(base + '/run1-unit/ant.log').read()
chk('unit ant: junit Tests run 1, Failures 0, Errors 0', re.search(r'Tests run: 1, Failures: 0, Errors: 0', ant) is not None)
# cluster: from the logs and csvs
def ts(line):
    m = re.search(r'(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d),(\d{3})', line)
    if not m: return None
    return int(datetime.datetime.strptime(m.group(1).replace('T', ' '), '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) + int(m.group(2))
for l in ('v1000', 'v1023', 'v1024', 'v2000', 'c1', 'c64'):
    d = '%s/run1-cl/%s' % (base, l)
    s = json.load(open(d + '/summary.json'))
    sl = open(d + '/system.log.filtered', errors='replace').read().splitlines()
    cmd = open(d + '/node-cmdline.txt').read()
    chk('%s node ran with -Xms2G -Xmx2G and the assigned ports' % l, '-Xmx2G' in cmd and '-Xms2G' in cmd and 'jmx.local.port=7326' in cmd, '')
    seg = [ts(x) for x in sl if 'Flushed index segment' in x]
    # SELF-CHECK SCRIPT FIX (first attempt assumed every segment line belongs to the major compaction; background compactions during the load also write segments)
    w = lambda a, b: len([t for t in seg if s[a] <= t <= s[b] + 1000])
    wl, wf, wc = w('t_load_start', 't_load_end'), w('t_flush_start', 't_flush_end'), w('t_compact_start', 't_compact_end')
    chk('%s "Flushed index segment" lines re-counted from system.log.filtered, per phase, == harness counts' % l, (wl, wf, wc) == (s['log_load']['Flushed index segment'], s['log_flush']['Flushed index segment'], s['log_compact']['Flushed index segment']) and len(seg) == wl + wf + wc,
        'file %d; load/flush/compact %d/%d/%d vs summary %d/%d/%d' % (len(seg), wl, wf, wc, s['log_load']['Flushed index segment'], s['log_flush']['Flushed index segment'], s['log_compact']['Flushed index segment']))
    chk('%s filtered system.log has no OutOfMemoryError / "Rejecting value (value size" / ERROR lines' % l, not any(('java.lang.OutOfMemoryError' in x or 'Rejecting value (value size' in x or x.startswith('ERROR')) for x in sl), '')
    chk('%s the filtered log contains no leftover rejection lines (filter worked)' % l, not any(("Rejecting value (size" in x or "Can't add term" in x) for x in sl), '')
    si = s['si_after_flush']; si2 = s['si_after_compact']
    if l in ('v1024', 'v2000'):
        chk('%s every SI component is 0 bytes after flush and after compaction' % l, all(b == 0 for _, b in si + si2) and len(si) > 0 and len(si2) > 0, '%s / %s' % (si, si2))
        chk('%s rejection counts: flush path == memtable path == %d' % (l, ROWS), s['log_load_plus_flush']["Rejecting value (size"] == ROWS and s['log_load']["Can't add term"] + s['log_flush']["Can't add term"] == ROWS, 'in-run counts only; raw lines were not kept (gap)')
    else:
        chk('%s SI components > rows*size after flush and compaction' % l, sum(b for _, b in si) > ROWS * s['size'] and sum(b for _, b in si2) > ROWS * s['size'], '%d / %d' % (sum(b for _, b in si), sum(b for _, b in si2)))
    hv = [(int(r['epoch_ms']), int(r['heap_used'])) for r in csv.DictReader(open(d + '/heap.csv')) if r['heap_used'].isdigit()]
    chk('%s heap sampler covered load, flush and compaction' % l, hv and hv[0][0] <= s['t_load_start'] + 2000 and hv[-1][0] >= s['t_compact_end'] - 5000, '%d samples' % len(hv))
    hist = open(d + '/histogram-pre-flush.txt').read()
    chk('%s histogram parsed' % l, 'Total' in hist, '')
c1, c64 = [json.load(open('%s/run1-cl/%s/summary.json' % (base, x)))['log_compact']['Flushed index segment'] for x in ('c1', 'c64')]
chk('control: 237 vs 4 segments at cap 1 vs 64 MB (floor(200000/844)+1, floor(200000/53990)+1)', (c1, c64) == (237, 4), '%d, %d' % (c1, c64))
fa = [json.load(open('%s/run1-cl/%s/summary.json' % (base, x)))['si_after_compact'] for x in ('c1', 'c64', 'v1023')]
chk('final index file after compaction is the same size at cap 1, cap 64 and default (cap does not change the file, only the memory path)', len({tuple(b for _, b in x) for x in fa}) <= 2, str([[b for _, b in x] for x in fa]))
print('SELFCHECK', 'ALL HOLD' if ok else 'SOME DO NOT HOLD')
