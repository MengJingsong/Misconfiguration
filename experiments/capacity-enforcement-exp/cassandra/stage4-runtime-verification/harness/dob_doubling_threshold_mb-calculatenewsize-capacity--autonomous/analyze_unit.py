# Checks B2g as amended (S4-A2) against the probe outputs. Usage: analyze_unit.py <dir with out-*.txt>
import re, sys, os, glob
d=sys.argv[1]; MiB=1<<20
# B2f final capacities and # resizes (copied from the frozen B2f table)
pred={('bytes',200):{0:(290565366,21),16:(254803968,15),64:(301989888,14),128:(268435456,13),1024:(268435456,13)},
      ('bytes',100):{0:(129140163,19),16:(113246208,13),64:(134217728,12),128:(134217728,12),1024:(134217728,12)},
      ('rows',200):{0:(306125095,15),16:(286668679,12),64:(226503648,10),128:(302004864,10),1024:(268448768,9)},
      ('rows',100):{0:(136055598,13),16:(127408302,10),64:(151002432,9),128:(134224384,8),1024:(134224384,8)}}
def parse(f):
    t=open(f).read()
    T=int(re.search(r'DOUBLING_THRESHOLD_MB=(-?\d+)',t).group(1))
    ex=[tuple(map(int,m.groups())) for m in re.finditer(r'EXPAND count=(\d+) (\d+) -> (\d+)',t)]
    fm=re.search(r'FINAL written=(\d+) capacity=(\d+)',t)
    return T,ex,int(fm.group(1)),int(fm.group(2)),('OVERFLOW' in t)
ok=True; C={}
for (mode,n),row in pred.items():
    for T,(pc,pr) in row.items():
        f=f'{d}/out-T{T}-{mode}{n}.txt'; Tr,ex,w,c,ov=parse(f); C[(mode,n,T)]=c
        ratio_ok=all((a==max(b*3//2,b+cnt)) if b>T*MiB else (a==max(2*b,b+cnt)) for cnt,b,a in ex)
        cell = (c==pc and len(ex)==pr and Tr==T and not ov and c>=w)
        ok &= cell and ratio_ok
        print(f'T={T:5d} {mode}{n}: read T={Tr} written={w} C={c} ({c/MiB:.2f} MiB) pred={pc} resizes={len(ex)}/{pr} C>=S={c>=w} ratio-rule={ratio_ok} cell-match={cell} maxtransient={max(a+b for _,b,a in ex)/MiB:.2f} MiB')
for mode in ('bytes','rows'):
    Tu,ex,w,c,ov=parse(f'{d}/out-unset-{mode}200.txt'); m=(Tu==64 and c==C[(mode,200,64)])
    ok&=m; print(f'unset {mode}200: read T={Tu} C={c} equals T=64: {m}')
    for T in (0,16,64,128,1024):
        r=C[(mode,200,T)]/C[(mode,100,T)]; ok&=1.5<=r<=2.25; print(f'  (v) {mode} T={T}: C200/C100={r:.4f} in [1.5,2.25]: {1.5<=r<=2.25}')
    seq=[C[(mode,200,T)] for T in (0,16,64,128,1024)]
    inc=all(seq[i]<seq[i+1] for i in range(4)); print(f'  (iii) {mode}200 C over T=0,16,64,128,1024 (MiB): {[round(x/MiB,2) for x in seq]}; strictly increasing: {inc}')
    near=[T for T in (16,64,128) if C[(mode,200,T)]<=2*T*MiB]; print(f'  row 2 (C<=2T MiB) for T in: {near}')
Tf,ex,w,c,ov=parse(f'{d}/out-fixed.txt'); print(f'fixed 200: OVERFLOW={ov} written={w} capacity={c} resizes={len(ex)}'); ok&=ov and c==1048576 and not ex
print('ROWS 2/3 NOT MET; B2g ROW 1 / ROW 5 ALL CHECKS:', ok)
