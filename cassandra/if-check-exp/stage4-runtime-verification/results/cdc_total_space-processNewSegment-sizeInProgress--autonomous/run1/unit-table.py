"""Prints one reading line per unit cell from run1/unit/<cell>/readings-excerpt.txt and cdc-verdict.txt (observation only). usage: unit-table.py <run1 dir>"""
import os,re,sys
MIB=1<<20
def kv(line): return dict(re.findall(r'(\w+)=("[^"]*"|\S+)', line))
base=os.path.join(sys.argv[1],'unit')
for name in sorted(os.listdir(base)):
    d=os.path.join(base,name)
    if not os.path.exists(os.path.join(d,'readings-excerpt.txt')): continue
    r={}
    for line in open(d+'/readings-excerpt.txt'):
        for tag in ('config','idle','writesDone','afterFlush2s','final','walkSum','sampler','afterUpdateCDCTotalSize'):
            if (' '+tag+' ') in line: r[tag]=kv(line)
        if ' walkSum ' in line: r['walk']=int(line.split()[-1])
    tr=open(d+'/cdc-verdict.txt').read().splitlines() if os.path.exists(d+'/cdc-verdict.txt') else []
    forb=sum(1 for l in tr if l.startswith('post') and 'FORBIDDEN' in l); dele=sum(1 for l in tr if l.startswith('deleteOld')); cre=sum(1 for l in tr if l.startswith('pre '))
    remaining=[int(re.search(r'remaining=(\d+)',l).group(1)) for l in tr if l.startswith('deleteOld')]
    r['rm']=0
    c=r['config'];f=r['final'];s=r['sampler'];a=r['afterFlush2s'];w=r['writesDone']
    print(f"{name:14s} acc={w['accepted']:>2} rej={w['rejected']:>2} peakB={int(s['peakBytes'])/MIB:6.1f} peakLinks={s['peakLinks']} afterFlush links={a['links']} B={int(a['duBytes'])/MIB:6.1f} final links={f['links']} du={int(f['duBytes'])/MIB:6.1f} trk={int(f['tracker'])/MIB:6.1f} walk={r['walk']/MIB:6.1f} created={cre} forb={forb} deleteOld={dele} minRem={min(remaining,default=0)/MIB:.1f}")
