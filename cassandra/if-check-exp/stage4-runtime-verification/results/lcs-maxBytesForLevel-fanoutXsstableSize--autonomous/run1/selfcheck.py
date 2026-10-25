#!/usr/bin/env python3
"""Independent self-check for lcs-maxBytesForLevel-fanoutXsstableSize--autonomous.
Does NOT reuse unit-analyze.py / cluster-analyze.py. Unit tier: re-derives every claim from the console copy of the readings in ant.log
(the logger echo of the same lines) and compares it with readings.txt. Cluster tier: re-parses the raw nodetool text, stress output, yaml and
node logs. usage: selfcheck.py <unit dir> <cluster dir>"""
import sys, re, os, glob, json, subprocess
UNIT, CL = sys.argv[1], sys.argv[2]; MIB = 1 << 20
out = []
def claim(n, ok, note): out.append(ok); print(f"[{'holds' if ok else 'DOES NOT HOLD'}] {n}: {note}")
# ---------------- unit
rd = {}
for l in open(f'{UNIT}/readings.txt'):
    p = l.rstrip('\n').split(' ', 3)
    if p[0] == 'R': rd[(p[1], p[2])] = p[3] if len(p) > 3 else ''
ant = {}
for l in open(f'{UNIT}/ant.log', errors='replace'):
    m = re.search(r'SubstituteLogger\.java:\d+ - R (\S+) (\S+) ?(.*)$', l)
    if m: ant[(m.group(1), m.group(2))] = m.group(3)
claim('U0 readings.txt and the console echo in ant.log hold the same readings', ant == rd and len(rd) > 450, f'{len(rd)} readings from file, {len(ant)} from ant.log')
txt = open(f'{UNIT}/ant.log', errors='replace').read()
claim('U0b ant reports 5 tests, 0 failures, 0 errors', bool(re.search(r'Tests run: 5, Failures: 0, Errors: 0', txt)), re.search(r'Tests run: .*', txt).group(0)[:90])
g = lambda sec, k: rd[(sec, k)]
bad = []; l0s = []
for s in (1, 2, 4):
    for f in (2, 10):
        for r in (1, 2, 3):
            t = f's{s}f{f}.rep{r}'
            l0 = int(g('step2', t + '.L0bytes')); l0s.append(l0)
            tgt = 4 * s * MIB; logged = float(g('step2', t + '.L0ratio'))
            if abs(l0 / tgt - logged) > 0.001 or g('step2', t + '.writeError') != 'none' or int(g('step2', t + '.sstables')) != 40: bad.append(t)
claim('U1 step 2: 18 runs, 40 L0 sstables each, no write error, logged ratio = L0 bytes / (4 x size x MiB)', not bad, f'L0 bytes {min(l0s)}..{max(l0s)} ({min(l0s)/MIB:.1f}-{max(l0s)/MIB:.1f} MiB); size-1 ratio {min(l0s)/(4*MIB):.2f}-{max(l0s)/(4*MIB):.2f}; size-4 {min(l0s)/(16*MIB):.2f}-{max(l0s)/(16*MIB):.2f}')
sums = []; below = 0
for s in (1, 2, 4):
    for f in (2, 10):
        for r in (1, 2, 3):
            t = f's{s}f{f}.rep{r}'
            lv = [int(x) for x in re.findall(r'\d+', g('step3', t + '.levelBytesAfter'))]
            if sum(lv) != int(g('step3', t + '.sumLevelBytesAfter')): below += 1000
            sums.append(sum(lv))
            if sum(lv) < int(g('step2', t + '.ingestedValueBytes')): below += 1
claim('U2 step 3: level bytes after draining sum to the logged total, never below the ingested value bytes, flat across knobs', below == 0 and max(sums) / min(sums) < 1.001, f'sum range {min(sums)}..{max(sums)} (spread {max(sums)/min(sums)-1:.5f})')
shape = []
for s, f in ((1, 10), (4, 2)):
    lv = [int(x) for x in re.findall(r'\d+', g('step3', f's{s}f{f}.rep1.levelBytesAfter'))]
    shape.append((s, f, [round(lv[i] / (f ** i * s * MIB), 3) for i in range(1, 5)]))
claim('U3 step 3: draining moves bytes between levels (L1 close to target) but not out of the table', all(sh[2][0] > 0.85 for sh in shape), str(shape))
ok = True; detail = []
for r in (1, 2, 3):
    w = g('step4', f'l8.rep{r}.warn'); m = re.search(r'has (\d+) bytes while its maximum size is supposed to be (\d+) bytes', w)
    ok &= bool(m) and int(m.group(1)) > int(m.group(2)) and g('step4', f'l8.rep{r}.candidate') == 'null' and g('step4', f'l8.rep{r}.warnCount') == '1' and g('step4', f'l8.rep{r}.sstableLevel') == '8'
    detail.append((m.group(1), m.group(2)) if m else None)
claim('U4 step 4: the L8 WARN text itself shows bytes > maximum, the call returned null, level was 8', ok, str(detail))
claim('U5 step 5: output sstable of the ~5 MiB partition is larger than the 1 MiB size option', all(int(g('step5', f'big.rep{r}.maxFile')) > MIB for r in (1, 2, 3)), str([int(g('step5', f'big.rep{r}.maxFile')) for r in (1, 2, 3)]))
claim('U6 step 6: 10^3 x 160 MiB = logged value, level 0 = 4 x size, overflow input throws', int(g('step6', 'maxBytesForLevel(3,10,160MiB)')) == 10 ** 3 * 160 * MIB and int(g('step6', 'maxBytesForLevel(0,10,160MiB)')) == 4 * 160 * MIB and g('step6', 'maxBytesForLevel(8,1000,2^40)') == 'RuntimeException', g('step6', 'maxBytesForLevel(3,10,160MiB)'))
c = {t: [int(g('step7', f'{t}.rep{r}.candidates')) for r in (1, 2, 3)] for t in ('mt4', 'mt32')}
claim('U7 step 7 control: candidates equal max_threshold (4 and 32) from 40 L0 sstables', c == {'mt4': [4] * 3, 'mt32': [32] * 3} and all(int(g('step7', f'{t}.rep{r}.l0sstables')) == 40 for t in c for r in (1, 2, 3)), str(c))
claim('U8 truncate control: all 18 ladder runs end at 0 bytes', sum(1 for k, v in rd.items() if k[0] == 'control' and v == '0') == 18, 'ok')
# ---------------- cluster
def tstat(path):
    t = open(path).read()
    lv = lambda key: [int(x) for x in re.findall(r'\d+', re.search(key + r': \[(.*?)\]', t).group(1))] if re.search(key + r': \[', t) else None
    return {'bytes': lv('SSTable bytes in each level'), 'count': lv('SSTables in each level'), 'live': int(re.search(r'Space used \(live\): (\d+)', t).group(1))}
CFGS = {'A': (10, 10, '8MiB/s', True), 'B': (160, 10, '8MiB/s', True), 'C': (10, 2, '8MiB/s', True), 'D': (None, None, '8MiB/s', True), 'Aprime': (10, 10, '0MiB/s', False)}
info = {}
for lb, (size, fan, thr, boost) in CFGS.items():
    d = f'{CL}/{lb}'
    st = open(f'{d}/stress-write.txt').read()
    errs = int(re.search(r'Total errors\s*:\s*(\d+)', st).group(1)); parts = int(re.search(r'Total partitions\s*:\s*([\d,]+)', st).group(1).replace(',', ''))
    cmd = open(f'{d}/commands.log').read(); yml = open(f'{d}/conf/cassandra.yaml').read()
    create = re.search(r'CREATE TABLE IF NOT EXISTS ks.standard1.*?compaction = (\{[^}]*\})', cmd).group(1)
    opt_ok = (('SizeTiered' in create) if size is None else (f"'sstable_size_in_mb':'{size}'" in create and f"'fanout_size':'{fan}'" in create))
    thr_ok = re.search(r'^compaction_throughput: (\S+)', yml, re.M).group(1) == thr and re.search(r'^concurrent_compactors: (\d+)', yml, re.M).group(1) == ('4' if lb == 'Aprime' else '1')
    boost_seen = 'setcompactionthroughput 0' in cmd
    syslog = open(f'{d}/logs/system.log', errors='replace').read()
    nerr = len(re.findall(r'^ERROR', syslog, re.M))
    lag, setl, trunc = (tstat(f'{d}/tablestats-{x}.txt') for x in ('lag-end', 'settled-write', 'truncated'))
    peak = 0; peaklive = 0
    for l in open(f'{d}/samples-standard1.jsonl'):
        r = json.loads(l)
        if 'tablestats' in r:
            m = re.search(r'SSTable bytes in each level: \[(.*?)\]', r['tablestats'])
            if m: peak = max(peak, int(re.findall(r'\d+', m.group(1))[0]))
            peaklive = max(peaklive, int(re.search(r'Space used \(live\): (\d+)', r['tablestats']).group(1)))
    peak = max(peak, lag['bytes'][0] if lag['bytes'] else 0); peaklive = max(peaklive, lag['live'], setl['live'])
    ex = open(f'{d}/exit.txt').read()
    info[lb] = dict(errs=errs, parts=parts, opt_ok=opt_ok, thr_ok=thr_ok, boost=boost_seen, nerr=nerr, lag=lag, setl=setl, trunc=trunc, peak=peak, peaklive=peaklive, ex=ex.strip(), sys_bytes=sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(d) for f in fs))
claim('C1 every run: table created with the labelled compaction options, yaml throughput/compactors as specified, stress finished with 0 errors and 2,000,000 partitions', all(i['opt_ok'] and i['thr_ok'] and i['errs'] == 0 and i['parts'] == 2000000 for i in info.values()), str({k: (i['opt_ok'], i['thr_ok'], i['errs'], i['parts']) for k, i in info.items()}))
claim('C2 the drain boost (setcompactionthroughput 0) was issued in A, B, C, D and not in Aprime', all(info[k]['boost'] == CFGS[k][3] for k in info), str({k: i['boost'] for k, i in info.items()}))
claim('C3 each node exited cleanly (rc=0, daemon stopped); no ERROR line in any system.log', all('rc=0 daemons_stopped=True' in i['ex'] and i['nerr'] == 0 for i in info.values()), str({k: (i['ex'], i['nerr']) for k, i in info.items()}))
T0 = lambda s: 4 * s * MIB
claim('C4 peak L0 bytes (raw tablestats text) is >= 10x L0 target in A and C (>= 400 MiB), and above B\'s 640 MiB target', all(info[k]['peak'] >= 10 * T0(10) and info[k]['peak'] >= 400 * MIB for k in 'AC') and info['B']['peak'] > T0(160), f"A {info['A']['peak']/MIB:.0f} B {info['B']['peak']/MIB:.0f} ({info['B']['peak']/T0(160):.2f}x) C {info['C']['peak']/MIB:.0f} MiB")
pl = [info[k]['peaklive'] for k in 'ABCD']; sl = [info[k]['setl']['live'] for k in 'ABCD']
claim('C5 peak live bytes and settled live bytes of A,B,C,D differ by less than 15% (here: less than 1%)', max(pl) / min(pl) < 1.15 and max(sl) / min(sl) < 1.15, f'peak live {[round(x/MIB) for x in pl]} MiB, settled {[round(x/MIB) for x in sl]} MiB, spreads {max(pl)/min(pl)-1:.4f} / {max(sl)/min(sl)-1:.4f}')
body = {}
for k, (s, f) in {'A': (10, 10), 'B': (160, 10), 'C': (10, 2), 'Aprime': (10, 10)}.items():
    lv = info[k]['setl']['bytes']; top = max(i for i, x in enumerate(lv) if x)
    body[k] = (lv[0], [round(lv[i] / (f ** i * s * MIB), 3) for i in range(1, top)], top)
claim('C6 after the drain L0 is empty and every level below the top sits at or below its target (ratios <= 1.001)', all(v[0] == 0 and all(r <= 1.001 for r in v[1]) for v in body.values()), str(body))
claim('C7 total live bytes before and after the drain agree within 1% (bytes moved between levels, none removed)', all(abs(info[k]['setl']['live'] / info[k]['lag']['live'] - 1) < 0.01 for k in 'ABCD' if info[k]['lag']['live']) and abs(info['Aprime']['setl']['live'] / info['Aprime']['lag']['live'] - 1) < 0.01, str({k: (round(i['lag']['live'] / MIB), round(i['setl']['live'] / MIB)) for k, i in info.items()}))
claim("C8 control A': fast compaction from the start lowers the peak L0 versus A and leaves settled bytes equal", info['Aprime']['peak'] < info['A']['peak'] and abs(info['Aprime']['setl']['live'] / info['A']['setl']['live'] - 1) < 0.01, f"A' {info['Aprime']['peak']/MIB:.0f} vs A {info['A']['peak']/MIB:.0f} MiB ({info['Aprime']['peak']/info['A']['peak']-1:+.1%})")
claim('C9 TRUNCATE control: raw tablestats after truncate shows 0 live bytes in every run', all(i['trunc']['live'] == 0 for i in info.values()), 'ok')
stopped = {lb: 'daemons left after stop: none' in open(f'{CL}/{lb}/commands.log').read() for lb in CFGS}
claim('C10 every run log records "daemons left after stop: none" (the live check of the node is made once at the end of the session)', all(stopped.values()), str(stopped))
print('SELF-CHECK:', 'ALL HOLD' if all(out) else f'{out.count(False)} DO NOT HOLD')
