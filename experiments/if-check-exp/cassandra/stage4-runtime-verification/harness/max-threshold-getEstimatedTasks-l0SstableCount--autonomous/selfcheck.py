#!/usr/bin/env python3
"""Independent self-check: re-derives the conclusion's inputs from the RAW files (not from phase-*.json, not through unit-analyze/cluster-analyze).
usage: selfcheck.py <unit dir> <cluster dir>"""
import sys, re, os, json, glob, datetime, xml.etree.ElementTree as ET
U, C = sys.argv[1], sys.argv[2]
bad = []
def say(ok, msg):
    print(('HOLDS  ' if ok else 'BROKEN ') + msg)
    if not ok: bad.append(msg)

# ---------------- unit: raw readings, junit xml, ant log
lines = [l.rstrip('\n') for l in open(f'{U}/readings.txt')]
say(len(lines) > 100, f'unit readings.txt has {len(lines)} lines')
xmls = glob.glob(f'{U}/TEST-*.xml')
if xmls:
    r = ET.parse(xmls[0]).getroot()
    say(r.get('tests') == '3' and r.get('failures') == '0' and r.get('errors') == '0', f"junit: tests={r.get('tests')} failures={r.get('failures')} errors={r.get('errors')}")
else: say(False, 'no junit xml')
say('BUILD SUCCESSFUL' in open(f'{U}/ant.log').read(), 'ant.log BUILD SUCCESSFUL')
est = {}
for l in lines:
    m = re.match(r'R step3 (on|off)\.seq(\d)\.mt(\d+)\.estimate (\d+)$', l)
    if m: est[(m.group(1), int(m.group(2)))] = (int(m.group(3)), int(m.group(4)))
say(len(est) == 14, f'14 estimate readings found ({len(est)})')
say(all(v[1] == 200 // v[0] for k, v in est.items() if k[0] == 'on'), 'every STCS-on estimate equals 200 // max_threshold: ' + str(sorted({v for k, v in est.items() if k[0] == 'on'})))
say(all(v[1] == 0 for k, v in est.items() if k[0] == 'off'), 'every STCS-off estimate is 0')
for key in ('sumOnDiskLength', 'liveDiskSpaceUsed', 'dataFiles', 'liveSSTables'):
    vals = {l.split()[-1] for l in lines if l.startswith('R step3') and l.split()[2].endswith('.' + key)}
    say(len(vals) == 1, f'unit {key} single value across 14 readings: {sorted(vals)}')
heaps = [(int(re.search(r'mt(\d+)', l.split()[2]).group(1)), int(l.split()[-1])) for l in lines if l.startswith('R step3') and l.split()[2].endswith('.heapUsed')]
mean = sum(h for _, h in heaps) / len(heaps)
say(max(h for _, h in heaps) - min(h for _, h in heaps) <= 0.05 * mean, f'unit heap max-min over all 14 readings = {max(h for _, h in heaps) - min(h for _, h in heaps)} B vs 5% of mean {0.05*mean:.0f}')
get = lambda k: [l.split()[-1] for l in lines if l.startswith('R ') and l.split()[2] == k]
say(get('size1.estimateByteTermOnly') and int(get('size1.estimateByteTermOnly')[0]) - int(get('size160.estimateByteTermOnly')[0]) > 50, f"control (a) byte term {get('size1.estimateByteTermOnly')} vs {get('size160.estimateByteTermOnly')}")
say(int(get('size1.maxOutput')[0]) < 1.5 * 2**20 and int(get('size160.maxOutput')[0]) > 10 * 2**20, f"control (b) max output {get('size1.maxOutput')} vs {get('size160.maxOutput')}")

# ---------------- cluster, per arm, from raw text
MT = {'mt4': 4, 'mt32': 32, 'mt128': 128, 'mt32b': 32, 'c64': 32, 'd32': 32}
tot = {}
for a, mt in MT.items():
    d = f'{C}/{a}'
    if not os.path.isdir(d): say(False, f'{a}: missing'); continue
    ts = open(f'{d}/tablestats-A.txt').read(); cs = open(f'{d}/compactionstats-A.txt').read()
    l0 = int(re.search(r'SSTables in each level: \[(\d+)', ts).group(1)); cnt = int(re.search(r'SSTable count: (\d+)', ts).group(1))
    pend = int(re.search(r'pending tasks\s+(\d+)', cs).group(1))
    l0b = int(re.search(r'SSTable bytes in each level: \[(\d+)', ts).group(1)); sz = 160 * 2**20
    bt = -(-max(0, l0b - int(4 * sz * 1.001)) // sz)   # ceil, written independently of the runner
    want = (0 if a == 'd32' else l0 // mt) + bt
    say(pend == want and cnt == l0, f'{a}: raw tablestats-A L0={l0} L0 bytes={l0b} sstable count={cnt}; raw compactionstats-A pending={pend}; expected {want} (byte term {bt})')
    ph = json.load(open(f'{d}/phase-A.json'))
    m = re.search(r'max\s*=\s*(\d+)', ph['thresholds'])
    say(m and int(m.group(1)) == mt, f'{a}: getcompactionthreshold says {ph["thresholds"].replace(chr(10)," ")}')
    cmd = open(f'{d}/commands.log').read()
    say(f"disable_stcs_in_l0={'true' if a == 'd32' else 'false'}" in cmd, f'{a}: JVM_EXTRA_OPTS in commands.log')
    say(re.search(r'Total errors\s*:\s*0', open(f'{d}/stress-write.tail.txt').read()) is not None, f'{a}: stress Total errors : 0')
    # samples: phase A boundaries, RssAnon and bytes during phase A
    S = [json.loads(l) for l in open(f'{d}/samples.jsonl') if l.strip()]
    S = [s for s in S if 'error' not in s]
    tB = json.load(open(f'{d}/phase-A.json'))['t']   # the end-of-phase-A record (the readings were taken at its start); enableautocompaction comes after it
    sa = [s for s in S if s['phase'] == 'A']
    say(len(sa) >= 8, f'{a}: {len(sa)} samples in phase A')
    bytesA = [s['bytes'] for s in sa]
    say(max(bytesA) - min(bytesA) < 0.01 * max(bytesA), f'{a}: table bytes constant through phase A ({min(bytesA)}..{max(bytesA)})')
    # compaction log lines for standard1 before the phase A end recorded (UTC in system.log)
    n = 0
    for f in glob.glob(f'{d}/logs/system.log') + glob.glob(f'{d}/logs/debug.log'):
        for l in open(f, errors='replace'):
            m2 = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d+)', l)
            if m2 and re.search(r'Compact(ing|ed)\b', l) and 'standard1' in l:
                t = datetime.datetime.strptime(m2.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp()
                if t < tB: n += 1
    say(n == 0, f'{a}: compaction log lines for standard1 before the phase A end record: {n}')
    pb = json.load(open(f'{d}/phase-B.json'))
    tot[a] = (ph['rssAnon'], ph['liveHeapHistogram'], ph['tableBytes'], pb['tablestats']['levels'][0], ph['tablestats']['levels'][0])
    say(open(f'{d}/exit.txt').read().strip() == 'rc=0 node_stopped=True', f'{a}: exit.txt ' + open(f'{d}/exit.txt').read().strip())
    tr = json.load(open(f'{d}/truncate.json')); say(tr['bytesAfterTruncate'] < 2**20, f'{a}: truncate control bytes {tr["bytesAfterTruncate"]}')
print('per-arm (rssAnon, liveHeap, tableBytes, L0 at B end, L0 at A end):')
for a, v in tot.items(): print(' ', a, v)
print('SELFCHECK', 'ALL HOLD' if not bad else 'BROKEN: ' + '; '.join(bad))
