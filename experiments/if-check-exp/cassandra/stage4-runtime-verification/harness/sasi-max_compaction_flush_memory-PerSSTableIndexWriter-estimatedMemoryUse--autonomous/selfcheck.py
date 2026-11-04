#!/usr/bin/env python3
"""Independent re-parse of the raw files (not via the analyzers). Usage: selfcheck.py <unit-raw-dir> <cluster-dir>"""
import csv, re, sys, glob, json, math
u, c = sys.argv[1], sys.argv[2]
bad = 0
def chk(n, ok, i=''):
    global bad; bad += (not ok); print('HOLDS' if ok else 'DOES NOT HOLD', n, i)
# unit: recompute from the cut list and results
rows = {r['arm']: r for r in csv.DictReader(open(u + '/unit-results.csv'))}
cuts = [l.strip().split(',') for l in open(u + '/unit-cuts.csv')][1:]
for arm, lim in [('comp-1', 1048576), ('comp-4', 4194304), ('comp-16', 16777216), ('comp-default', 161061273), ('flush-1', 1073741824)]:
    n = -(-lim // 224); mine = [x for x in cuts if x[0] == arm]
    chk('unit ' + arm + ' cuts', len(mine) == 100000 // n and all(int(x[3]) == n * 224 for x in mine) and int(rows[arm]['segments_before_complete']) == len(mine), 'n=%d cuts=%d' % (n, len(mine)))
chk('unit final index has all terms in every arm', all(int(r['final_terms']) == 100000 for r in rows.values()))
# cluster: re-count lines in the per-arm log excerpts, JVM args, SI files, sampler-based peaks
cmd = open(c + '/node-cmdline.txt').read()
chk('node heap 3G', '-Xmx3G' in cmd and '-Xms3G' in cmd and 'jmx.local.port=7332' in cmd)
exp = {'a1-1024': 0, 'a2-8': 81, 'a3-32': 21, 'a4-128': 6, 'a5-def': 5, 'a6-1024': 0}
for lab, e in exp.items():
    t = open('%s/segments-%s.txt' % (c, lab)).read()
    n = len(re.findall(r'Flushed index segment', t)); f = len(re.findall(r'Index flush to', t))
    chk('cluster %s segment lines %d (exp %d), index-flush lines %d' % (lab, n, e, f), n == e and f == 1)
    chk('cluster %s no errors/OOM in excerpt' % lab, open('%s/errors-%s.txt' % (c, lab)).read().strip() == '')
s = json.load(open(c + '/summary.json'))
chk('one sstable, no error key', len(s['data_files']) == 1 and 'error' not in s, s['data_files'])
sizes = {a['label']: a['si_after'][0][1] for a in s['arm_results']}
chk('index file size identical across caps', len(set(sizes.values())) == 1, sizes)
chk('index dropped after every arm', all(a['si_after_drop'] == [] for a in s['arm_results']))
pk = {}
for lab in exp:
    base = [a for a in s['arm_results'] if a['label'] == lab][0]['baseline_histo']['total_bytes']
    vals = [json.loads(l).get('total_bytes', 0) - base for l in open('%s/histo-%s.jsonl' % (c, lab))]
    pk[lab] = max(vals); 
print('peaks MB', {k: round(v / 1e6) for k, v in pk.items()}, 'samples', {l: sum(1 for _ in open('%s/histo-%s.jsonl' % (c, l))) for l in exp})
chk('peak order 8<32<128<def<1024 and 1024 arms agree within 5%', pk['a2-8'] < pk['a3-32'] < pk['a4-128'] < pk['a5-def'] < pk['a1-1024'] and abs(pk['a1-1024'] - pk['a6-1024']) / pk['a1-1024'] < 0.05)
# old-gen after-GC from the JMX sampler, independent column read
hdr = open(c + '/pool.csv').readline().strip().split(','); io = hdr.index('old_after_gc')
rowsP = [l.split(',') for l in open(c + '/pool.csv').read().splitlines()[1:] if l.count(',') == len(hdr) - 1]
og = {}
for a in s['arm_results']:
    og[a['label']] = max(int(r[io]) for r in rowsP if a['t_start'] <= int(r[0]) <= a['t_end'] + 8000)
print('old after GC MB', {k: round(v / 1e6) for k, v in og.items()})
chk('post-GC old gen ordered by cap', og['a2-8'] < og['a3-32'] < og['a4-128'] < og['a5-def'] < og['a1-1024'])
print('BAD', bad); sys.exit(1 if bad else 0)
