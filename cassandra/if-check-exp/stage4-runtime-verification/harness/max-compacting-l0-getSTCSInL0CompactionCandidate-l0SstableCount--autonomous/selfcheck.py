#!/usr/bin/env python3
"""Independent self-check (step 4) for max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.
Re-derives the verdict from RAW files with code that shares nothing with unit-analyze.py / cluster-analyze.py:
  unit:    the console echo in ant.log and the JUnit XML system-out (not readings.txt), compared with readings.txt
  cluster: raw tablestats-*.txt, raw sampled tablestats text in samples.jsonl, flushes.log, stress-write.txt, debug.log,
           conf/cassandra.yaml, jvm-args.txt, exit.txt
usage: selfcheck.py <unit outdir> <cluster outdir (with A B C D)>"""
import sys, os, re, json, glob, collections
U, C = sys.argv[1], sys.argv[2]
ok_all = []
def say(ok, msg):
    ok_all.append(ok); print(('HOLDS     ' if ok else 'DOES NOT HOLD ') + msg)

# ------------------------------------------------------------------ unit
echo = {}
for l in open(os.path.join(U, 'ant.log'), errors='replace'):
    m = re.search(r' - R (\S+) (\S+) (.*)$', l.rstrip('\n'))
    if m: echo[m.group(2)] = m.group(3)
xml = ''.join(open(f, errors='replace').read() for f in glob.glob(os.path.join(U, 'TEST-*.xml')))
xml_keys = dict((m.group(2), m.group(3)) for m in re.finditer(r'(?m)^R (\S+) (\S+) (.*)$', xml))
rd = {}
for l in open(os.path.join(U, 'readings.txt')):
    p = l.rstrip('\n').split(' ', 3)
    if p[0] == 'R' and len(p) > 3: rd[p[2]] = p[3]
say(set(echo) == set(rd) and all(echo[k] == rd[k] for k in rd), f'unit: console echo in ant.log ({len(echo)} keys) equals readings.txt ({len(rd)} keys)')
if xml_keys: say(all(xml_keys.get(k) == rd[k] for k in rd), f'unit: JUnit XML system-out ({len(xml_keys)} keys) equals readings.txt')
hd = re.search(r'<testsuite [^>]*>', xml); hd = hd.group(0) if hd else ''
at = {k: re.search(k + r'="(\d+)"', hd) for k in ('tests', 'errors', 'failures')}
say(all(at.values()) and at['errors'].group(1) == '0' and at['failures'].group(1) == '0', f'unit: JUnit XML testsuite header {hd[:160]} (errors and failures 0)')

def cand(prefix):
    if rd.get(prefix + '.candidate') == 'null': return ('null',)
    return (rd[prefix + '.stcs'], int(rd[prefix + '.size']), int(rd[prefix + '.level']), rd[prefix + '.inputLevels'])
# table of outcomes per (route, N, flag), identical across tables/reps?
by = collections.defaultdict(set)
for k in rd:
    mm = re.match(r'(R[012])\.(mt\d+)\.rep(\d+)\.N(\d+)\.flag(true|false)\.candidate$', k)
    if mm:
        route, tab, rep, n, flag = mm.groups(); pre = k[:-len('.candidate')]
        by[(route, tab, int(n), flag)].add(cand(pre))
stable = all(len(v) == 1 for v in by.values())
say(stable, f'unit: every (route, table, N, flag) cell gives the same candidate in all reps ({len(by)} cells)')
def one(route, tab, n, flag): return next(iter(by[(route, tab, n, flag)]))
exp_ok = True; notes = []
for tab, mt in (('mt32', 32), ('mt8', 8)):
    for n in (31, 32, 33, 64, 200):
        a = one('R1', tab, n, 'false'); b = one('R2', tab, n, 'false'); r0 = one('R0', tab, n, 'false')
        stcs1 = a[0] == 'true'; stcs2 = b[0] == 'true'; stcs0 = r0[0] == 'true'
        if stcs0 or any(one('R0', tab, n, 'true')[0] == 'true' for _ in [0]): exp_ok = False; notes.append(('R0 stcs', tab, n))
        if (n >= 33) != stcs1: exp_ok = False; notes.append(('R1 boundary', tab, n, a))
        if (n >= 33) != stcs2: exp_ok = False; notes.append(('R2 boundary', tab, n, b))
        if stcs1 and a[1] != mt: exp_ok = False; notes.append(('R1 size', tab, n, a))
        if stcs2 and b[1] != mt: exp_ok = False; notes.append(('R2 size', tab, n, b))
        if one('R1', tab, n, 'true')[0] == 'true' or one('R2', tab, n, 'true') != ('null',): exp_ok = False; notes.append(('flag true', tab, n))
say(exp_ok, 'unit: STCS candidate appears exactly from N=33 on routes R1 and R2, size = max_threshold, never on R0, never with the flag true' + (' ' + str(notes[:3]) if notes else ''))
say(all(rd[k] == 'none' for k in rd if k.endswith('.error')) and all(rd[f'R0.{t}.rep{r}.N200.l0sstables'] == '200' for t in ('mt32', 'mt8') for r in range(1, 4) if f'R0.{t}.rep{r}.N200.l0sstables' in rd), 'unit: no exception, 200 L0 sstables exist on R0 (nothing refused)')
ctl = [(int(rd[f'ctl.rep{r}.L1before']), int(rd[f'ctl.rep{r}.L1after']), int(rd[f'ctl.rep{r}.L1target'])) for r in range(1, 4) if f'ctl.rep{r}.L1after' in rd]
say(len(ctl) >= 1 and all(b0 > 2.5 * t and b1 <= 1.001 * t for b0, b1, t in ctl), f'unit: positive control L1 bytes (before, after, target) {ctl}')
ex = []
for t, mt in (('mt32', 32), ('mt8', 8)):
    for n in (33, 64):
        for r in range(1, 4):
            k = f'exec.{t}.N{n}.rep{r}'
            if k + '.l0after' in rd: ex.append(int(rd[k + '.l0before']) - int(rd[k + '.l0after']) == mt - 1)
say(bool(ex) and all(ex), f'unit: one executed STCS task removes max_threshold-1 sstables from L0 ({len(ex)} arms)')

# ------------------------------------------------------------------ cluster
def tsl(txt, key):
    m = re.search(rf'{key}: \[(.*?)\]', txt)
    return [int(x.split('/')[0].strip() or 0) for x in m.group(1).split(',')] if m else None
def label(lb):
    d = os.path.join(C, lb); o = {'d': d}
    o['lag'] = open(f'{d}/tablestats-lag-end.txt').read()
    o['samples'] = [json.loads(l) for l in open(f'{d}/samples.jsonl')]
    o['stress'] = open(f'{d}/stress-write.txt').read()
    o['flushes'] = [json.loads(l) for l in open(f'{d}/flushes.log')]
    o['yaml'] = open(f'{d}/conf/cassandra.yaml').read()
    o['jvm'] = open(f'{d}/jvm-args.txt').read()
    o['exit'] = open(f'{d}/exit.txt').read().strip()
    dbg = [open(p, errors='replace').read() for p in glob.glob(f'{d}/logs/debug.log*')]
    o['stcs'] = [l for t in dbg for l in t.splitlines() if 'L0 is too far behind' in l]
    return o
L = {lb: label(lb) for lb in 'ABCD' if os.path.isdir(os.path.join(C, lb))}
def peak(o):
    v = [tsl(s['tablestats'], 'SSTables in each level')[0] for s in o['samples'] if 'tablestats' in s and tsl(s['tablestats'], 'SSTables in each level')]
    v.append(tsl(o['lag'], 'SSTables in each level')[0]); return max(v)
def firstexceed(o):
    for s in o['samples']:
        if 'tablestats' in s:
            lv = tsl(s['tablestats'], 'SSTables in each level')
            if lv and lv[0] > 32: return s['t']
    return None
P = {lb: peak(o) for lb, o in L.items()}
print('INFO peak L0 per label (re-parsed from raw tablestats text):', P)
for lb, o in L.items():
    say('rc=0' in o['exit'] and 'daemons_stopped=True' in o['exit'], f'{lb}: exit.txt "{o["exit"]}"')
    err = int(re.search(r'Total errors\s*:\s*(\d+)', o['stress']).group(1)); rows = int(re.search(r'Total partitions\s*:\s*([\d,]+)', o['stress']).group(1).replace(',', ''))
    say(err == 0 and rows == 1500000, f'{lb}: stress errors {err}, partitions {rows}')
    say(all(f['rc'] == 0 for f in o['flushes']), f'{lb}: {len(o["flushes"])} nodetool flush calls, all rc 0')
    live_mb = int(re.search(r'Space used \(live\): (\d+)', o['lag']).group(1)) / 2**20
    print(f'INFO {lb}: lag-end live {live_mb:.0f} MiB; per-level counts {tsl(o["lag"], "SSTables in each level")}; stcs debug lines {len(o["stcs"])}')
spec = {'A': ('1MiB/s', False), 'B': ('1MiB/s', False), 'C': ('1MiB/s', True), 'D': ('0MiB/s', False)}
for lb, o in L.items():
    thr, flag = spec[lb]
    say(re.search(rf'^compaction_throughput: {thr}', o['yaml'], re.M) is not None and (('disable_stcs_in_l0=true' in o['jvm']) == flag), f'{lb}: yaml compaction_throughput {thr}, JVM flag disable_stcs_in_l0={flag}')
if all(k in L for k in 'ABCD'):
    written = 1500000 * 1050 / 2**20
    for lb in 'ABC':
        live = int(re.search(r'Space used \(live\): (\d+)', L[lb]['lag']).group(1)) / 2**20
        d = L[lb]['d']; fb = json.load(open(f'{d}/snapshot-lag-end.json'))['bytes'] / 2**20
        say(abs(fb / live - 1) < 0.15 and 0.8 < live / written < 1.3, f'{lb}: lag-end file bytes {fb:.0f} MiB vs tablestats live {live:.0f} MiB vs rows x ~1050 B = {written:.0f} MiB')
    say(P['A'] >= 100 and P['B'] >= 100 and P['C'] >= 100, f'peak L0 A,B,C = {P["A"]}, {P["B"]}, {P["C"]} (>= 100)')
    fl = len(L['B']['flushes']); b_lag = tsl(L['B']['lag'], 'SSTables in each level')[0]; b_files = len(json.load(open(L['B']['d'] + '/snapshot-lag-end.json'))['datafiles'])
    say(b_lag >= 100 and b_lag == b_files and b_lag <= fl, f'B: L0 at lag-end {b_lag} = Data.db files on disk {b_files} (no compaction: every sstable is an L0 flush output), <= {fl} flush calls (a call with nothing dirty makes no sstable)')
    say(len(L['A']['stcs']) >= 1 and len(L['C']['stcs']) == 0 and len(L['B']['stcs']) == 0, f'debug lines: A {len(L["A"]["stcs"])}, B {len(L["B"]["stcs"])}, C {len(L["C"]["stcs"])}')
    say(P['D'] < 0.5 * P['A'], f'D peak L0 {P["D"]} < half of A peak {P["A"]}')
    # first debug line vs first sample above 32
    fa = firstexceed(L['A'])
    print('INFO A first sampled L0>32 at', fa, '; first debug line:', L['A']['stcs'][:1])
    import datetime
    first = L['A']['stcs'][0]; ts = datetime.datetime.strptime(re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)', first).group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp()
    near = [s for s in L['A']['samples'] if 'datafiles' in s and s['t'] <= ts + 1]
    print('INFO A: Data.db files in the 5-s sample just before the first debug line:', near[-1]['datafiles'] if near else None, 'at', round(ts - near[-1]['t'], 1), 's before it')
    say(bool(near) and near[-1]['datafiles'] >= 33, 'A: the first debug line is not before the L0 count exceeds 32 (Data.db files >= 33 at the last 5-s sample before it; the line is only written when the count is above 32, :306)')
    for lb in 'ACD':
        s = json.load(open(f"{L[lb]['d']}/snapshot-settled-write.json")); tx = open(f"{L[lb]['d']}/tablestats-settled-write.txt").read()
        by = tsl(tx, 'SSTable bytes in each level'); cnt = tsl(tx, 'SSTables in each level')
        top = max(i for i, x in enumerate(by) if x)
        nominal = lambda i: (10 ** i) * 10 * 2**20
        rat = [by[i] / nominal(i) for i in range(1, top)]
        live0 = int(re.search(r'Space used \(live\): (\d+)', L[lb]['lag']).group(1)); live1 = int(re.search(r'Space used \(live\): (\d+)', tx).group(1))
        say(all(r <= 1.05 for r in rat) and abs(live1 / live0 - 1) < 0.05 and cnt[0] <= (4 if lb == 'D' else 32), f'{lb}: settled per-level bytes {by}, below-top ratios {[round(r,3) for r in rat]}, L0 count {cnt[0]}, live {live1/2**20:.0f} vs {live0/2**20:.0f} MiB')
    for lb, o in L.items():
        t = json.load(open(f"{o['d']}/snapshot-truncated.json"))['bytes']; ref = json.load(open(f"{o['d']}/snapshot-{'settled-write' if lb != 'B' else 'lag-end'}.json"))['bytes']
        say(t < 0.01 * ref, f'{lb}: truncate control {t} bytes vs {ref}')
print('SELF-CHECK:', 'ALL HOLD' if all(ok_all) else f'{ok_all.count(False)} DO NOT HOLD')
