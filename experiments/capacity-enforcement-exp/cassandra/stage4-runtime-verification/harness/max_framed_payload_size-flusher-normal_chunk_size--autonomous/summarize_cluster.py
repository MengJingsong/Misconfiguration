import sys
cell=None; rows=[]
for line in open(sys.argv[1]):
    p=line.strip().split(',')
    if p[0]=='CELL': cell={'tag':p[1], **dict(x.split('=',1) for x in p[2:])}; cell['s']={}; rows.append(cell)
    elif p[0]=='SAMPLE': cell['s'][p[1]]={k:int(v) for k,v in (x.split('=') for x in p[2:])}
    elif p[0]=='RESULT': cell['res']=','.join(p[1:])
    elif p[0]=='SUPPORT': cell['sendq']=int(p[1].split('=')[1]); cell['rss']=p[2]
MiB=1<<20
print("tag,K,M,mode,rep,baseline_used,held_used,Delta_MiB,held_size-overflow_MiB,held_overflow_MiB,after-baseline_used,sendQ_MiB,result,Delta+sendQ_MiB")
for r in rows:
    b,h,a=r['s']['baseline'],r['s']['held'],r['s']['after']
    d=h['used']-b['used']
    print(f"{r['tag']},{r['K']},{r['M']},{r['mode']},{r['rep']},{b['used']},{h['used']},{d/MiB:.2f},{(h['size']-h['overflow'])/MiB:.2f},{h['overflow']/MiB:.2f},{a['used']-b['used']},{r['sendq']/MiB:.2f},{r['res']},{(d+r['sendq'])/MiB:.2f}")
