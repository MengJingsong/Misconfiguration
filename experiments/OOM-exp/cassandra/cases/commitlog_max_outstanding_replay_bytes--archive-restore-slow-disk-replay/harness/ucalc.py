import sys,re,os
for f in sys.argv[1:]:
    d={}
    tot=0
    for l in open(f):
        p=l.split()
        if l.startswith('Total'): tot=int(p[2]); continue
        if len(p)>=4 and p[0].endswith(":") and p[1].isdigit(): d[p[3]]=(int(p[1]),int(p[2]))
    if not tot: print(f, 'no data'); continue
    M=2**20
    ac=d.get('org.apache.cassandra.db.rows.ArrayCell',(0,0)); bc=d.get('org.apache.cassandra.db.rows.BufferCell',(0,0))
    b=d.get('[B',(0,0)); mut=d.get('org.apache.cassandra.db.Mutation',(0,0))[0]
    memb=20.1*M*bc[0]/944105
    U=ac[1]+ac[0]*16+ac[0]*48+max(0,b[1]-memb)
    K=mut*63.7*1024
    print(f"{f.split('/runs/')[-1]:22s} live={tot/M:6.0f} Mut={mut:5d} K={K/M:5.1f}MiB ArrayCell={ac[0]:8d} U={U/M:6.0f}MiB U/mut={(U/M/mut if mut else 0):.2f} BufferCell={bc[0]:8d} U/K={(U/K if K else 0):.1f}")
