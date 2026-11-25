import sys, re, collections, math
rows=[]; cell=None
for line in open(sys.argv[1]):
    line=line.strip()
    if line.startswith('CELL,'): cell=dict(kv.split('=') for kv in line[5:].split(','))
    elif line.startswith('RESULT,'):
        r=dict(kv.split('=') for kv in line[7:].split(',')); r['cell']=cell; rows.append(r)
    elif line.startswith('AFTER_RELEASE,'): rows[-1]['after']=int(line.split('=')[1])
def ru(v): return ((v+31)//32)*32 if v<1024 else ((v+2047)//2048)*2048
g=collections.OrderedDict()
for r in rows:
    c=r['cell']; key=(c['K'],int(c['N']),c['codec'],c['cache']); g.setdefault(key,[]).append(r)
print("Kset,Kreported,N,codec,cacheMiB,reps,frames,maxFrame,wire,wire_pred,dUsed(min..max),dUsed/N,pred_dUsed,dOverflow(max),dSize(max),after(max)")
for (K,N,codec,cache),rs in g.items():
    k=int(rs[0]['K']); F=math.ceil((N+9)/(k-6)) if codec=='crc' else None
    if codec=='crc':
        full=F-1; last=(N+9)-full*(k-6); pred=full*ru(k+4)+ru(last+10); wp=N+9+10*F
    else: pred=None; wp=None
    du=[int(r['dUsed']) for r in rs]
    ks=set(r['K'] for r in rs)
    print(f"{K},{'/'.join(ks)},{N},{codec},{cache},{len(rs)},{'/'.join(sorted(set(r['frames'] for r in rs)))},{'/'.join(sorted(set(r['maxFrame'] for r in rs)))},{'/'.join(sorted(set(r['wire'] for r in rs)))},{wp},{min(du)}..{max(du)},{max(du)/N:.4f},{pred},{max(int(r['dOverflow']) for r in rs)},{max(int(r['dSize']) for r in rs)},{max(r.get('after',-1) for r in rs)}")
