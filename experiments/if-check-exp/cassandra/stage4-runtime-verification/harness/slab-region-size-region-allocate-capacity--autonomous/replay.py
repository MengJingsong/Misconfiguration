import sys
def sim(n, s, cap, maxclone=131072):
    if s>maxclone: return dict(regions=0, real=0, unslab=n*s)
    regions=0; off=None
    for _ in range(n):
        while True:
            if off is None: regions+=1; off=0
            new=off; off+=s
            if new+s<=cap: break
            off=None
    return dict(regions=regions, real=regions*cap, unslab=0)
M=1<<20
for cap in (M//2, M, 2*M):
    for s in (116509,131072,100000,4096,131073):
        r=sim(400,s,cap); o=400*s
        print(cap,s,r, 'owns',o, 'ratio', round(r['real']/o,5) if r['real'] else None, 'waste', r['real']-o)
for L in (64,128):
  for s in (116509,131072):
    n=(L*M)//s
    r=sim(n,s,M); print('limit',L,s,'n',n,'owns',n*s,r,'real/L',r['real']/(L*M),'real/owns',r['real']/(n*s))
# cluster row model: key 4 + value S, interleaved
def simrows(rows,S,cap=M):
    seq=[]
    for _ in range(rows): seq+=[4,S]
    regions=0; off=None
    for s in seq:
        while True:
            if off is None: regions+=1; off=0
            new=off; off+=s
            if new+s<=cap: break
            off=None
    return regions
for S in (116509,131068,131072):
    for rows in (4000,):
        reg=simrows(rows,S); ch=rows*(S+4)
        print('rows',S,rows,'regions',reg,'real',reg*M,'charged',ch,'ratio',reg*M/ch, 'steady', M/ (( M//(S+4))*(S+4)) , M//(S+4))
