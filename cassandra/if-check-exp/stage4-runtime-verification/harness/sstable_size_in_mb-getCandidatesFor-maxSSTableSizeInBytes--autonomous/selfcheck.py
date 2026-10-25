#!/usr/bin/env python3
"""Independent self-check for sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous.
Does not reuse unit-analyze.py / cluster-analyze.py. Unit: the console echo of the readings in ant.log against readings.txt, claims re-derived
from the raw numbers. Cluster: raw nodetool tablestats text (counts, live bytes, per-level bytes), the sampler's own file listing, stress output,
yaml, commands.log, system.log. usage: selfcheck.py <unit dir> <cluster dir>"""
import sys, re, os, json
UNIT, CL = sys.argv[1], sys.argv[2]; MIB = 1 << 20
out = []
def claim(n, ok, note): out.append(ok); print(f"[{'holds' if ok else 'DOES NOT HOLD'}] {n}: {note}")
rd = {}
for l in open(f'{UNIT}/readings.txt'):
    p = l.rstrip('\n').split(' ', 3)
    if p[0] == 'R': rd[(p[1], p[2])] = p[3] if len(p) > 3 else ''
ant = {}
for l in open(f'{UNIT}/ant.log', errors='replace'):
    m = re.search(r'SubstituteLogger\.java:\d+ - R (\S+) (\S+) ?(.*)$', l)
    if m: ant[(m.group(1), m.group(2))] = m.group(3)
claim('U0 readings.txt equals the console echo in ant.log', ant == rd and len(rd) > 100, f'{len(rd)} vs {len(ant)} readings')
txt = open(f'{UNIT}/ant.log', errors='replace').read()
claim('U0b ant reports 3 tests, 0 failures, 0 errors', bool(re.search(r'Tests run: 3, Failures: 0, Errors: 0', txt)), re.search(r'Tests run: .*', txt).group(0)[:80])
g = lambda s, k: rd[(s, k)]
ok = True; det = []
for n in (1, 5):
    for r in (1, 2, 3):
        t = f'N{n}.rep{r}'
        cb, sb = int(g('step3', t + '.candidateBytes')), int(g('step3', t + '.sizeBytes'))
        ok &= sb == n * MIB and cb > sb and g('step3', t + '.candidateHasL1') == 'true' and int(g('step3', t + '.candidateCount')) == 7
        det.append(round(cb / sb, 2))
claim('U1 N=1 and 5: candidate bytes exceed the size option and all 7 sstables (6 L0 + the L1 one) are candidates', ok, f'candidate/size ratios {det}')
ok = True; det = []
for r in (1, 2, 3):
    t = f'N160.rep{r}'
    cb, sb = int(g('step3', t + '.candidateBytes')), int(g('step3', t + '.sizeBytes'))
    ok &= sb == 160 * MIB and cb < sb and g('step3', t + '.candidateHasL1') == 'false' and g('step3', t + '.candidateOutputLevel') == '0' and int(g('step3', t + '.candidateCount')) == 6
    det.append(round(cb / sb, 3))
claim('U2 N=160: 6 L0 candidates only (no L1), total below the size, output level 0', ok, f'ratios {det}')
ok = True; det = []
for r in (1, 2, 3):
    sizes = [int(x) for x in re.findall(r'\d+', g('step4', f'out5.rep{r}.outputSizes'))]
    inb = int(g('step4', f'out5.rep{r}.inputBytes')); osum = int(g('step4', f'out5.rep{r}.outputSum'))
    ok &= len(sizes) >= 2 and max(sizes) <= 5 * MIB + 200 * 1024 and abs(osum / inb - 1) < 0.01 and sum(sizes) == osum
    det.append((len(sizes), round(max(sizes) / MIB, 3), round(osum / inb, 4)))
claim('U3 step 4: the size-5 task writes >= 2 files, none above 5 MiB + 200 KiB, outputs sum to the input within 1%', ok, str(det))
claim('U4 step 4: the ~12 MiB partition ends as one file above the 5 MiB option', all(int(g('step4', f'big5.rep{r}.maxFile')) > 5 * MIB for r in (1, 2, 3)), str([int(g('step4', f'big5.rep{r}.maxFile')) for r in (1, 2, 3)]))
p1 = [int(g('step5', f'p1.rep{r}.L0bytes')) for r in (1, 2, 3)]; p160 = [int(g('step5', f'p160.rep{r}.L0bytes')) for r in (1, 2, 3)]
claim('U5 phase 2: 200 L0 sstables, none above level 0, L0 bytes = live bytes; size 1 and 160 equal within 0.1%', all(g('step5', f'{t}.rep{r}.sstables') == '200' and g('step5', f'{t}.rep{r}.notL0') == '0' and g('step5', f'{t}.rep{r}.L0bytes') == g('step5', f'{t}.rep{r}.liveBytes') for t in ('p1', 'p160') for r in (1, 2, 3)) and all(abs(a / b - 1) < 0.001 for a, b in zip(p1, p160)), f'p1 {p1} p160 {p160}; size-1 L0 target {int(g("step5","p1.rep1.L0target"))}, size-160 L0 target {int(g("step5","p160.rep1.L0target"))}')
claim('U6 truncate control: 6 runs at 0 bytes', sum(1 for k, v in rd.items() if k[0] == 'control' and v == '0') == 6, 'ok')
# ---------------- cluster
def rawstats(path):
    t = open(path).read()
    lv = lambda key: [int(re.split(r'/', x.strip())[0]) for x in re.search(key + r': \[(.*?)\]', t).group(1).split(',')] if re.search(key + r': \[', t) else None
    return dict(count=int(re.search(r'SSTable count: (\d+)', t).group(1)), live=int(re.search(r'Space used \(live\): (\d+)', t).group(1)), total=int(re.search(r'Space used \(total\): (\d+)', t).group(1)), lvb=lv('SSTable bytes in each level'))
SIZE = {'N5': 5, 'N160': 160, 'N1024': 1024, 'S160': 160}
info = {}
for lb, n in SIZE.items():
    d = f'{CL}/{lb}'
    st = open(f'{d}/stress-write.txt').read(); cmd = open(f'{d}/commands.log').read(); yml = open(f'{d}/conf/cassandra.yaml').read()
    errs = int(re.search(r'Total errors\s*:\s*(\d+)', st).group(1)); parts = int(re.search(r'Total partitions\s*:\s*([\d,]+)', st).group(1).replace(',', ''))
    opt = re.search(r"'sstable_size_in_mb':'(\d+)'", re.search(r'CREATE TABLE IF NOT EXISTS ks.standard1.*', cmd).group(0)).group(1) == str(n)
    thr = re.search(r'^compaction_throughput: (\S+)', yml, re.M).group(1) == '16MiB/s' and re.search(r'^concurrent_compactors: (\d+)', yml, re.M).group(1) == '1'
    sec = lb == 'S160'; sec_ok = ('setcompactionthroughput 1\n' in cmd or 'setcompactionthroughput 1 ' in cmd or re.search(r'setcompactionthroughput 1\s*$', cmd, re.M) is not None) == sec
    boost = 'setcompactionthroughput 0' in cmd
    lag, setl, trunc = (rawstats(f'{d}/tablestats-{x}.txt') for x in ('lag-end', 'settled-write', 'truncated'))
    peak = lag['lvb'][0]; last = None
    for l in open(f'{d}/samples-standard1.jsonl'):
        r = json.loads(l)
        if 'tablestats' in r:
            m = re.search(r'SSTable bytes in each level: \[(.*?)\]', r['tablestats'])
            if m: peak = max(peak, int(re.split(r'/', m.group(1).split(',')[0])[0]))
        if r.get('bytes') is not None: last = r if r.get('bytes', 0) else last
    syslog = open(f'{d}/logs/system.log', errors='replace').read()
    info[lb] = dict(errs=errs, parts=parts, opt=opt, thr=thr, sec_ok=sec_ok, boost=boost, lag=lag, setl=setl, trunc=trunc, peak=peak, nerr=len(re.findall(r'^ERROR', syslog, re.M)), ex=open(f'{d}/exit.txt').read().strip(), stopped='daemons left after stop: none' in cmd)
claim('C1 every run: CREATE TABLE carries the labelled sstable_size_in_mb, yaml 16 MiB/s and 1 compactor, 0 stress errors, 2,000,000 partitions', all(i['opt'] and i['thr'] and i['errs'] == 0 and i['parts'] == 2000000 for i in info.values()), str({k: (i['opt'], i['thr'], i['errs'], i['parts']) for k, i in info.items()}))
claim('C2 S160 alone was throttled to 1 MiB/s at start (setcompactionthroughput 1 in its command log); all runs issued the drain boost', info['S160']['sec_ok'] and all(i['boost'] for i in info.values()), str({k: (i['sec_ok'], i['boost']) for k, i in info.items()}))
claim('C3 clean exits (rc=0, daemon stopped, "daemons left after stop: none"), no ERROR line in any system.log', all('rc=0 daemons_stopped=True' in i['ex'] and i['stopped'] and i['nerr'] == 0 for i in info.values()), str({k: (i['nerr'], i['stopped']) for k, i in info.items()}))
main = ['N5', 'N160', 'N1024']
lv = [info[k]['setl']['live'] for k in main]; tot = [info[k]['setl']['total'] for k in main]
claim('C4 settled live bytes (Cassandra\'s own count) within 10% across N=5,160,1024', max(lv) / min(lv) < 1.10 and max(tot) / min(tot) < 1.10, f'live {[round(x/MIB) for x in lv]} MiB; spread {max(lv)/min(lv)-1:.4f}')
mean = {k: info[k]['setl']['live'] / info[k]['setl']['count'] / MIB for k in main}
cnt = {k: info[k]['setl']['count'] for k in main}
claim('C5 positive control: Cassandra\'s SSTable count and mean file size follow N (count falls, mean grows with N)', cnt['N5'] > cnt['N160'] > cnt['N1024'] and mean['N5'] < mean['N160'] < mean['N1024'], f'counts {cnt}; mean file MiB {({k: round(v,1) for k, v in mean.items()})}')
claim('C6 N=5 and N=160: mean file within 0.7N..1.1N (levels hold files of the option size)', all(0.7 * n <= mean[k] <= 1.1 * n for k, n in (('N5', 5), ('N160', 160))), f"{mean['N5']:.2f} (N=5), {mean['N160']:.1f} (N=160)")
claim('C7 N=1024: 2 files of about the option size (mean 1000-1030 MiB of 2 GiB live): the option, not the data volume, bounds the file (the prediction wording "bounded by the data volume" was imprecise)', cnt['N1024'] == 2 and 1000 <= mean['N1024'] <= 1030, f"count {cnt['N1024']}, mean {mean['N1024']:.0f} MiB of {info['N1024']['setl']['live']/MIB:.0f} MiB live")
claim('C8 N=1024: the L0 target (4,096 MiB) was not reached (peak L0 below it) -> filed "limit never reached" row for that N', info['N1024']['peak'] < 4096 * MIB, f"peak L0 {info['N1024']['peak']/MIB:.0f} MiB")
claim('C9 S160 (1 MiB/s): L0 bytes exceeded 4 x 160 = 640 MiB with 0 write errors', info['S160']['peak'] > 640 * MIB and info['S160']['errs'] == 0, f"peak L0 {info['S160']['peak']/MIB:.0f} MiB; lag-end per-level bytes {info['S160']['lag']['lvb']}")
claim('C10 TRUNCATE control: raw tablestats shows 0 live bytes afterwards in all 4 runs', all(i['trunc']['live'] == 0 for i in info.values()), 'ok')
print('SELF-CHECK:', 'ALL HOLD' if all(out) else f'{out.count(False)} DO NOT HOLD')
