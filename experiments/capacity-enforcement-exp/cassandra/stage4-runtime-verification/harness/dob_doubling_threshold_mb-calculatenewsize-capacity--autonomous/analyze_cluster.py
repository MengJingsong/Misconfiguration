# Checks B3g as amended (S4-A3) against JfrDob outputs. Usage: analyze_cluster.py <jfr dir>
import sys, re, glob, os
from datetime import datetime
d=sys.argv[1]; MiB=1<<20; S=209715200
pred={'unset':216.0,'0':291.9,'16':273.4,'64':216.0,'128':288.0,'1024':256.0}
predctl={'unset':144.0,'64':144.0,'1024':128.0}
def ts(s):
    s=s.rstrip('Z'); a,b=s.split('.'); return datetime.strptime(a,'%Y-%m-%dT%H:%M:%S').timestamp()+float('0.'+b)
def bursts(f):
    ev=[]
    for line in open(f):
        p=line.split()
        if len(p)==4: ev.append((ts(p[0]),p[1],int(p[3])-16))
    ev.sort(); out=[]; cur=[]
    for e in ev:
        if cur and e[0]-cur[-1][0]>2.0: out.append(cur); cur=[]
        cur.append(e)
    if cur: out.append(cur)
    return out
def ratio_ok(caps,T):
    ok=True
    for a,b in zip(caps,caps[1:]):
        if a<MiB: continue
        r=b/a
        lim=(T if T is not None else 64)*MiB
        if a<=lim: good=abs(r-2.0)<=0.001 or b<=a+1100000  # 2.0, or prev + one write's remainder (<= ~1 MiB value)
        else: good=abs(r-1.5)<=0.001 or (b>a*1.5 and b<=a+1100000)
        ok&=good
    return ok
res={}; allok=True
for T in ['unset','0','16','64','128','1024']:
    Tn=None if T=='unset' else int(T)
    for kind in ['','-ctl']:
        f=f'{d}/T{T}{kind}.txt'
        if not os.path.exists(f): print('missing',f); allok=False; continue
        bs=bursts(f)
        Cs=[max(c for _,_,c in b) for b in bs]
        thr=[sorted(set(t for _,t,_ in b)) for b in bs]
        print(f'T={T}{kind}: {len(bs)} bursts; per-burst largest capacity (MiB): {[round(c/MiB,4) for c in Cs]}; threads {thr}')
        for b in bs:
            caps=[c for _,_,c in b]
            print(f'    burst caps (MiB): {[round(c/MiB,2) for c in caps]} ratio-rule={ratio_ok(caps,Tn)}')
        reads=open(f'{d}/T{T}{kind}-reads.txt').read()
        lens=re.findall(r'len (\d+)',reads)
        res[T+kind]=(Cs,[ratio_ok([c for _,_,c in b],Tn) for b in bs],lens)
print()
for T in ['unset','0','16','64','128','1024']:
    Cs,rr,lens=res[T]; ctl=res[T+'-ctl'][0]
    C=max(Cs) if Cs else 0
    c1=len(Cs)==3 and all(c>=S for c in Cs); c2=all(abs(c/MiB-pred[T])<=1 for c in Cs); c3=all(rr); c4=(max(Cs)-min(Cs))<=0.1*MiB
    c5=lens==['1048576']*3
    # control: per query (3 queries) the largest over its internal pages; queries 5 s apart -> bursts
    ctlC=max(ctl) if ctl else 0
    c6=ctlC<=0.75*C
    allok&=c1 and (c2 or c3) and c4 and c5 and c6
    print(f'T={T}: 3 queries C>=S {c1}; within 1 MiB of B3f {pred[T]} {c2}; ratio rule {c3}; 3 agree within 0.1 MiB {c4}; returned 1 MiB x3 {c5}; ctl largest {ctlC/MiB:.2f} MiB <= 0.75*{C/MiB:.2f} {c6}' + (f' (B3f ctl {predctl[T]})' if T in predctl else ''))
Cm={T:max(res[T][0]) for T in ['unset','0','16','64','128','1024']}
nm=Cm['64']<Cm['1024']<Cm['128']; allok&=nm
print(f"C(64)={Cm['64']/MiB:.2f} < C(1024)={Cm['1024']/MiB:.2f} < C(128)={Cm['128']/MiB:.2f}: {nm}; unset==64: {Cm['unset']==Cm['64']}")
seq=[Cm[t] for t in ['0','16','64','128','1024']]; print('row 3 strictly increasing over T:', all(seq[i]<seq[i+1] for i in range(4)))
print('row 2 (C<=2T MiB for T=16 or 64):', [t for t in ['16','64'] if Cm[t]<=2*int(t)*MiB])
print('B3g ROW 1 / ROW 5 ALL CHECKS:', allok)
