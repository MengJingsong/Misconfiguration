import sys, re, collections
path, run = sys.argv[1], sys.argv[2]
lines=[l.split() for l in open(path)]
ev=[(l[0], dict(x.split('=',1) for x in l[1:] if '=' in x)) for l in lines]
# pass 1: fate of each malloc (by order): which alloc frees it, or race, or live at end
live={}; fate={}; L=0; maxL=0; maxi=None; idx_of={}
win=re.search(r'T_A0=(\d+) T_A1=\d+ T_C0=\d+ T_STOP=(\d+)', open(f'{run}/summary.txt').read()); t0,t1=map(int,win.groups())
for i,(k,f) in enumerate(ev):
    ms=int(f['ms'])
    if k=='malloc':
        live[f['peer']]=(i,int(f['cap'])); L+=int(f['cap'])
    elif k=='free':
        j,c=live.pop(f['peer']); L-=c; fate[j]=('discard',f.get('alloc')) if f['site']=='discard' else ('race',None)
    if t0<=ms<=t1 and L>maxL: maxL,maxi=L,i
for p,(j,c) in live.items(): fate[j]=('end',None)
# replay to maxi, classify live regions
live={}; 
for i,(k,f) in enumerate(ev[:maxi+1]):
    if k=='malloc': live[f['peer']]=(i,int(f['cap']))
    elif k=='free': live.pop(f['peer'],None)
by=collections.Counter(); byalloc=collections.Counter(); caps=collections.Counter()
for p,(j,c) in live.items():
    fa=fate.get(j,('?',None)); by[fa[0]]+=c
    if fa[0]=='discard': byalloc[fa[1]]+=c
    if fa[0] in ('race','end'): caps[c]+=1
owns={f['alloc']:int(f['owns']) for k,f in ev if k=='discard'}
dms={f['alloc']:int(f['ms']) for k,f in ev if k=='discard'}
M=1048576
print(f'max L {maxL/M:.2f} MiB at line {maxi} ms {ev[maxi][1]["ms"]}')
print('live bytes by fate:', {k:round(v/M,2) for k,v in by.items()})
for a,c in byalloc.most_common(8):
    print(f'  alloc {a}: regions live at peak {c/M:.2f} MiB; owns at its discard {owns[a]/M:.2f} MiB; discard ms {dms[a]}')
print('  sum owns(at discard) of allocators live at peak:', round(sum(owns[a] for a in byalloc)/M,2), 'MiB')
print('race/end regions live at peak by cap:', sorted(caps.items()))
