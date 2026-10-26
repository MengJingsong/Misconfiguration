#!/usr/bin/env python3
"""Independent self-check (stage 4): re-parses the raw files without the analyzers' code paths.
Usage: selfcheck.py <unit-run-dir> <cluster-out-dir> <gz-dir>   (unit-run-dir has raw/writer-results.csv and ant.log; gz-dir has <label>-system.log.gz)
Prints HOLDS / DOES NOT HOLD per part; exit 1 if any does not hold."""
import sys, os, csv, json, gzip, re, math, datetime
unit, cl, gz = sys.argv[1:4]
bad = 0
def part(name, ok, note):
    global bad
    print('%-62s %s  %s' % (name, 'HOLDS' if ok else 'DOES NOT HOLD', note))
    if not ok: bad += 1

# ---- unit tier: recompute from the CSV with first-principles arithmetic
rows = list(csv.reader(open(unit + '/raw/writer-results.csv')))
hdr, data = rows[0], rows[1:]
R = [dict(zip(hdr, r)) for r in data]
ant = open(unit + '/ant.log', errors='replace').read()
part('U0 test passed in ant.log', 'BUILD SUCCESSFUL' in ant and re.search(r'Tests run: 1, Failures: 0, Errors: 0', ant) is not None, 'BUILD SUCCESSFUL, Tests run: 1, Failures: 0')
def find(arm, size=None, n=None, opt=None, src=None):
    return [r for r in R if r['arm'] == arm and (size is None or int(r['size']) == size) and (n is None or int(r['n_adds']) == n) and (opt is None or r['option_mb'] == opt) and (src is None or r['source'].upper() == src)]
per = lambda s: 64 + 48 + s + 60 + 40 + 8
ok = True; notes = []
for s in (1022, 1023):
    r = find('boundary', s, 10000)[0]; ok &= int(r['est_final']) == 10000 * per(s) and int(r['info_reject_lines']) == 0
for s in (1024, 1025):
    r = find('boundary', s, 10000)[0]; ok &= int(r['est_final']) == 0 and int(r['info_reject_lines']) == 10000 and int(r['file_len']) == 0 and int(r['err_reject_lines']) == 0
part('U1 boundary: 1022/1023 accepted, 1024/1025 rejected, file length 0', ok, 'est = N*(S+220); 10000 INFO lines at 1024/1025')
g = {n: find('growth', 1023, n)[0] for n in (1000, 10000, 100000)}
ok = all(int(g[n]['est_final']) == n * per(1023) for n in g) and all(int(g[n]['file_len']) >= n * 1023 for n in g)
part('U2 growth: estimate = N*1243 for N in 1k/10k/100k, file >= N*1023', ok, ' '.join('%d:%s/%s' % (n, g[n]['est_final'], g[n]['file_len']) for n in g))
ok = True
for opt, cap in (('1', 1 << 20), ('8', 8 << 20), ('def', 161061273)):
    r = find('cap', 1023, 100000, opt, 'COMPACTION')[0]
    cmin = math.ceil(cap / per(1023)); cuts = 100000 // cmin; lines = cuts + (1 if cuts and 100000 % cmin else 0)
    ok &= int(r['cuts_before_complete']) == cuts and int(r['segment_lines']) == lines
part('U3 cap control cuts floor(N/ceil(cap/1243)) and lines for options 1/8/default', ok, 'expected 118/119, 14/15, 0/0')
ests = [r for r in csv.reader(open(unit + '/raw/writer-estimates.csv')) if r and r[4] == 'cut']
c1 = [int(r[6]) for r in ests if r[0] == 'cap' and r[3] == '1']
part('U4 estimate at every cut of the 1 MiB arm is in [cap, cap+1243)', len(c1) == 118 and all((1 << 20) <= v < (1 << 20) + 1243 for v in c1), 'cuts=%d' % len(c1))
t = find('token', None, 1, 'def', 'COMPACTION')[0]; t1 = find('token', None, 1, '1', 'COMPACTION')[0]
part('U5 tokenized: 131072 words accepted, estimate 227*131072, one cut under option 1', int(t['est_final']) == 227 * 131072 and int(t['info_reject_lines']) == 0 and int(t1['cuts_before_complete']) == 1, 'est=%s, value bytes=%s' % (t['est_final'], t['size']))

# ---- cluster tier: re-parse the filtered log by timestamp, and the full log for the rejection totals
def ts(line):
    m = re.search(r'(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d),(\d{3})', line)
    if not m: return None
    return datetime.datetime.strptime(m.group(1).replace('T', ' '), '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000 + int(m.group(2))
for label, tabl in (('m', 't'), ('c1', 't'), ('c16', 't'), ('tc', 'tc')):
    d = json.load(open('%s/%s/summary.json' % (cl, label)))
    flt = open('%s/%s/system.log.filtered' % (cl, label), errors='replace').read().splitlines()
    t0, t1 = d['t_compact_start'], d['t_compact_end']
    segs_c = [l for l in flt if 'Flushed index segment' in l and 'SI_t_a_idx' in l and ts(l) is not None and t0 - 2000 <= ts(l) <= t1]
    segs_all = [l for l in flt if 'Flushed index segment' in l]
    part('C1 %s: compaction-window segment lines for t_a_idx (re-counted from the filtered log)' % label, len(segs_c) == d['log_compact'].get('flushed_segment_t_a_idx', 0), '%d (summary %s); all segment lines in the run: %d' % (len(segs_c), d['log_compact'].get('flushed_segment_t_a_idx', 0), len(segs_all)))
    ok = all(sum(v for k, v in d[sec]['si'].items() if k.endswith('SI_' + n + '.db')) == d[sec]['si_bytes_by_index'][n] for sec in ['files_after_compact'] for n in ('t_a_idx', 't_b_idx', 'tc_c_idx'))
    part('C2 %s: per-index bytes equal the sum of the listed SI files' % label, ok, str(d['files_after_compact']['si_bytes_by_index']))
    oom = any(('java.lang.OutOfMemoryError' in l or 'OutOfMemoryError:' in l) and 'HeapDumpOnOutOfMemoryError' not in l for l in flt)
    heap = [int(r['heap_used']) for r in csv.DictReader(open('%s/%s/heap.csv' % (cl, label)))]
    cmdl = open('%s/%s/node-cmdline.txt' % (cl, label)).read()
    part('C3 %s: no OOM in the log; heap samples < 2 GiB; command line has Xmx2G and JMX 7330' % label, not oom and max(heap) < 2 * 2 ** 30 and '-Xmx2G' in cmdl and '7330' in cmdl, 'peak used %.0f MiB over %d samples' % (max(heap) / 2 ** 20, len(heap)))
    path = '%s/%s-system.log.gz' % (gz, label)
    cnt = {'cant_b': 0, 'cant_all': 0, 'wr_b': 0, 'wr_a': 0, 'wr_c': 0, 'wr_all': 0}
    with gzip.open(path, 'rt', errors='replace') as f:
        for l in f:
            if "Can't add term" in l:
                cnt['cant_all'] += 1; cnt['cant_b'] += (" of column b " in l)
            elif 'Rejecting value (size' in l:
                cnt['wr_all'] += 1
                for c in 'abc':
                    if ') for column %s (analyzed' % c in l: cnt['wr_' + c] += 1
    if label == 'm':
        part("C4 m: full-log totals: Can't add term b = 400000; writer-path rejections b = 800000 (flush + compaction), a = 0", cnt['cant_b'] == 400000 and cnt['wr_b'] == 800000 and cnt['wr_a'] == 0 and cnt['cant_all'] == 400000 and cnt['wr_all'] == 800000, str(cnt))
    else:
        part('C4 %s: full-log rejection lines are all zero' % label, cnt['cant_all'] == 0 and cnt['wr_all'] == 0, str(cnt))
print('SELFCHECK', 'ALL HOLD' if not bad else '%d DO NOT HOLD' % bad)
sys.exit(1 if bad else 0)
