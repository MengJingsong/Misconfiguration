#!/usr/bin/env python3
"""Independent self-check (different parsing route than analyze_*.py): python3 selfcheck.py <run1-dir> [P].
Re-derives the cluster facts from session.log, system.log.full, stress-*.out, hist-*.txt and jmx.txt, and the unit facts from unit.txt."""
import sys, os, re, ast, json, glob
R = sys.argv[1]; P = int(sys.argv[2]) if len(sys.argv) > 2 else 1000000; MIB = 1 << 20; bad = 0
def ok(name, cond, detail=''):
    global bad
    print(('HOLDS ' if cond else 'FAILS  ') + name + (' | ' + detail if detail else '')); bad += (not cond)
# ---- unit: recompute from raw lines without the analyzer's regex helper
for l in open(R + '/unit/raw/unit.txt'):
    t = l.split()
    if t[0] == 'fill':
        f = dict(x.split('=') for x in t[1:]); C = int(f['cap'])
        ok('unit fill %sMiB x%s threads: settled weight <= C and size == C/1024' % (f['capMiB'], f['threads']), int(f['weightedSize_settled']) <= C and int(f['size_settled']) == C // 1024)
    if t[0] == 'guard' and 'sum=' in l:
        s = int(re.search(r'sum=(\d+)', l).group(1)); threw = 'IllegalArgumentException' in l
        ok('unit guard %s: throws iff sum > Integer.MAX_VALUE' % t[1], threw == (s > 2**31 - 1), 'sum=%d threw=%s' % (s, threw))
# ---- cluster: session.log dicts
sess = open(R + '/cluster/session.log').read()
arms = [a for a in ('k0', 'k4', 'k16', 'k64', 'k512', 'k16b', 'rt') if os.path.isdir(R + '/cluster/' + a)]
info = {}
for a in arms:
    d = R + '/cluster/' + a; seg = sess.split('=== arm %s ' % a)[1].split('=== arm')[0]
    knob = int(re.search(r'key_cache_size (\d+) MiB', '=== arm %s ' % a + seg).group(1))
    syslog = open(d + '/system.log.full').read()
    inits = re.findall(r'Initializing key cache with capacity of (\d+) MiBs', syslog)
    ok('%s: system.log initialised the key cache with %d MiB (last init line)' % (a, knob), inits and int(inits[-1]) == knob, str(inits[-1:]))
    ends = {m.group(1): ast.literal_eval(m.group(2)) for m in re.finditer(r'\] (end-pass1|end-pass2|after-setcap) (\{.*\})', seg)}
    for p in ('pass1', 'pass2'):
        txt = open(d + '/stress-%s.out' % p).read()
        tp = int(re.search(r'Total partitions\s*:\s*([\d,]+)', txt).group(1).replace(',', '')); er = int(re.search(r'Total errors\s*:\s*(\d+)', txt).group(1))
        ok('%s %s: stress read 3,000,000 partitions with 0 errors' % (a, p), tp == 3000000 and er == 0, 'partitions=%d errors=%d' % (tp, er))
    def heap(fn):
        n = {}; tot = 0
        for line in open(fn):
            w = line.split()
            if len(w) == 4 and w[0].endswith(':'): n[w[3]] = (int(w[1]), int(w[2]))
        kck = n.get('org.apache.cassandra.cache.KeyCacheKey', (0, 0)); rie = n.get('org.apache.cassandra.io.sstable.format.big.RowIndexEntry', (0, 0))
        nodes = sum(b for k, (c, b) in n.items() if k.startswith('com.github.benmanes.caffeine.cache.') and re.fullmatch(r'[A-Z]+', k.rsplit('.', 1)[1]))
        return kck[0], kck[1] + rie[1] + nodes + kck[0] * 40
    e2 = ends['end-pass2']; n2, hb = heap(d + '/hist-end-pass2.txt'); n1, hb1 = heap(d + '/hist-end-pass1.txt')
    jm = json.load(open(d + '/jmx.txt'))
    jsize = int(jm['Size'].split('\n')[-1]); jcap = int(jm['Capacity'].split('\n')[-1]); jent = int(jm['Entries'].split('\n')[-1])
    ok('%s: JMX Capacity == knob MiB and histogram KeyCacheKey instances ~ Entries' % a, jcap == (16 if a == 'rt' else knob) * MIB and abs(n2 - jent) <= 0.01 * max(jent, 1) + 50, 'jmx entries=%d hist instances=%d' % (jent, n2))
    ok('%s: JMX Size <= Capacity' % a, jsize <= jcap, '%d <= %d' % (jsize, jcap))
    info[a] = dict(knob=knob, size=e2['size'], ent=e2['entries'], hb=hb, hb1=hb1, size1=ends['end-pass1']['size'])
    print('      %s: size=%d entries=%d heap(KeyCacheKey+RowIndexEntry+nodes+key arrays)=%d factor=%.3f' % (a, e2['size'], e2['entries'], hb, hb / e2['size'] if e2['size'] else 0))
for a in ('k4', 'k16', 'k64', 'k16b'):
    if a in info:
        i = info[a]; ok('%s: Size within 1%% of the cap and heap bytes did not grow in pass 2' % a, i['size'] >= .99 * i['knob'] * MIB and i['size'] <= i['knob'] * MIB and i['hb'] <= 1.05 * i['hb1'])
if all(a in info for a in ('k4', 'k16', 'k64')):
    r = [info[a]['hb'] for a in ('k4', 'k16', 'k64')]; ok('heap bytes ratio ~1:4:16', abs(r[1] / r[0] / 4 - 1) < .15 and abs(r[2] / r[0] / 16 - 1) < .15, str(r))
if 'k512' in info: ok('k512: not at cap, grows past pass 1, entries >= 0.95 P', info['k512']['size'] < 512 * MIB * .5 and info['k512']['size'] > info['k512']['size1'] and info['k512']['ent'] >= .95 * P, str(info['k512']))
if 'k0' in info: ok('k0: no entries, no size', info['k0']['ent'] == 0 and info['k0']['size'] == 0)
print('SELFCHECK FAILS:', bad); sys.exit(1 if bad else 0)
