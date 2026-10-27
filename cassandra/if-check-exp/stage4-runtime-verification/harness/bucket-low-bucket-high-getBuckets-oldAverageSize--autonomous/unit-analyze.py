#!/usr/bin/env python3
"""Judge B2f/B2g (amended 2026-10-26) from readings.txt.   usage: unit-analyze.py <readings.txt>
Prints PASS/FAIL lines (each a frozen B2f statement or an instrument check) and a SUMMARY line. Exit 0 always."""
import sys, re, collections
R = collections.OrderedDict()
for l in open(sys.argv[1]):
    m = re.match(r'R (\S+) (\S+) (.*)$', l.rstrip('\n'))
    if m: R[(m.group(1), m.group(2))] = m.group(3)
def g(s, k): return R[(s, k)]
def gi(s, k): return int(g(s, k))
res = []
def chk(name, ok, detail, kind='B2f'): res.append((kind, name, ok)); print(('PASS ' if ok else 'FAIL ') + f'[{kind}] ' + name + ' :: ' + detail)
def lst(x): return [int(v) for v in re.findall(r'\d+', x)]
def model(sizes, high, low, minsz):   # same model as model-predict.py
    B = []
    for s in sorted(sizes):
        c = [b for b in B if (s > b[0]*low and s < b[0]*high) or (s < minsz and b[0] < minsz)]
        if c:
            b = c[-1]; b[0] = int((len(b[1])*b[0] + s)//(len(b[1])+1)); b[1].append(s)
        else: B.append([s, [s]])
    return B
MIB = 1 << 20
T, MX = 15472761705, 3571443917
chk('geo list total/max as modelled', gi('syn','geo.total') == T and gi('syn','geo.max') == MX, f"{g('syn','geo.total')} {g('syn','geo.max')}", 'instrument')
exp = {  # (list, minMiB, setting): (buckets, largestFiles, largestBytes)
 ('geo',0,'narrow'):(32,1,MX), ('geo',0,'default'):(11,2,6318708469), ('geo',0,'wide'):(1,32,T),
 ('geo',50,'narrow'):(18,1,MX), ('geo',50,'default'):(7,2,6318708469), ('geo',50,'wide'):(1,32,T)}
for (l, mn, s), (b, f, by) in exp.items():
    k = f'{l}.min{mn}.{s}'
    chk(f'synthetic {k}: {b} buckets, largest {f} files / {by} B', gi('syn',k+'.buckets')==b and gi('syn',k+'.largestFiles')==f and gi('syn',k+'.largestBytes')==by, f"buckets={g('syn',k+'.buckets')} files={g('syn',k+'.largestFiles')} bytes={g('syn',k+'.largestBytes')}")
for mn in (0, 50):
    for s in ('narrow','default','wide'):
        k = f'eq.min{mn}.{s}'
        chk(f'equal list {k}: 1 bucket of 32 files, 3355443200 B', gi('syn',k+'.buckets')==1 and gi('syn',k+'.largestFiles')==32 and gi('syn',k+'.largestBytes')==3355443200, f"{g('syn',k+'.buckets')} {g('syn',k+'.largestFiles')} {g('syn',k+'.largestBytes')}")
SET = {'nar':(0.9,1.1),'def':(0.5,1.5),'wid':(0.01,100.0),'ctl':(0.01,100.0)}
for t in SET:
    sz = lst(g(t,'sizes')); tot = gi(t,'totalBytes')
    chk(f'{t}: 12 live sstables, ascending, consecutive ratios in [1.10,1.20]', gi(t,'live')==12 and len(sz)==12 and all(1.10 <= b/a <= 1.20 for a,b in zip(sz,sz[1:])), f"ratios={[round(b/a,3) for a,b in zip(sz,sz[1:])]}", 'instrument')
    mb = model(sz, SET[t][1], SET[t][0], 0)
    chk(f'{t}: static getBuckets counts equal the stand-alone model on the measured sizes', sorted([len(b[1]) for b in mb], reverse=True) == lst(g(t,'static.counts')), f"model={sorted([len(b[1]) for b in mb], reverse=True)} real={g(t,'static.counts')}", 'instrument')
chk('nar: 12 buckets of one, no task', gi('nar','static.buckets')==12 and g('nar','real.taskNull')=='true', f"buckets={g('nar','static.buckets')} taskNull={g('nar','real.taskNull')}")
dc = lst(g('def','static.counts'))
chk('def: two buckets, each 4 to 8 files; task of 4 to 8 inputs', len(dc)==2 and all(4<=c<=8 for c in dc) and g('def','real.taskNull')=='false' and 4<=gi('def','real.inputs')<=8, f"counts={dc} inputs={g('def','real.inputs')}")
chk('wid: one bucket of 12; task of all 12 inputs = total bytes', gi('wid','static.buckets')==1 and gi('wid','real.inputs')==12 and gi('wid','real.inputBytes')==gi('wid','totalBytes'), f"inputs={g('wid','real.inputs')} bytes={g('wid','real.inputBytes')} total={g('wid','totalBytes')}")
chk('ctl: thresholds 4/4; task of exactly 4 inputs; input bytes below the wide task', g('ctl','thresholds')=='4/4' and gi('ctl','real.inputs')==4 and gi('ctl','real.inputBytes')<gi('wid','real.inputBytes'), f"thr={g('ctl','thresholds')} inputs={g('ctl','real.inputs')} bytes={g('ctl','real.inputBytes')}")
for t in ('def','wid','ctl'):
    r = gi(t,'real.peakExtra')/gi(t,'real.inputBytes')
    chk(f'{t}: executed; peak extra / input bytes in [0.8,1.15]', 0.8 <= r <= 1.15, f"ratio={r:.3f} peakExtra={g(t,'real.peakExtra')} inputBytes={g(t,'real.inputBytes')}")
    chk(f'{t}: sampler took >= 20 samples during the task (instrument)', gi(t,'real.samples')>=20, g(t,'real.samples'), 'instrument')
    chk(f'{t}: after the task fewer sstables than 12', gi(t,'real.sstablesAfter')<12, g(t,'real.sstablesAfter'), 'instrument')
chk('peak extra ordered wide > default > wide/max4 > narrow (0)', gi('wid','real.peakExtra')>gi('def','real.peakExtra')>gi('ctl','real.peakExtra')>0, f"wid={g('wid','real.peakExtra')} def={g('def','real.peakExtra')} ctl={g('ctl','real.peakExtra')}")
chk('truncate empties every table', all(g(t,'bytesAfterTruncate')=='0' for t in SET), 'bytesAfterTruncate', 'instrument')
bad = [n for k,n,ok in res if not ok]
print('SUMMARY', 'ALL PASS (matches B2f; B2g row 1, row 3, with the control moving)' if not bad else 'FAILURES: ' + '; '.join(bad))
