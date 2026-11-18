import csv,os,re,glob
M='/mydata/s4/r7-w1/mirror'
def load(n):
    d=os.path.join(M,n); a=open(d+'/args.txt').read()
    ls=int(re.search(r'(\d+) load start',a)[1]); le=int(re.search(r'(\d+) load end',a)[1])
    dead=re.search(r'(\d+) V dead',a); dead=int(dead[1]) if dead else None
    st=[int(re.search(r'start epoch_ms=(\d+)',open(f).read())[1]) for f in glob.glob(d+'/load-*.log') if re.search(r'start epoch_ms=(\d+)',open(f).read())]
    ss=min(st); rows=[r for r in csv.DictReader(open(d+'/samples.csv')) if r['direct_used'] not in ('NA','-1','')]
    return ls,ss,dead or le,rows,dead
def frac(rows,t0,t1):
    w=[r for r in rows if t0<=int(r['epoch_ms'])<=t1]; return sum(int(r['mut_active'])>=32 for r in w),len(w)
arms=sorted(d for d in os.listdir(M) if os.path.isfile(os.path.join(M,d,'outcome.txt')) and not d.startswith('SHAKE'))
print('arm | dead | L-window first 70s | S-window first 55s | S window 55-end')
for n in arms:
    ls,ss,end,rows,dead=load(n)
    a=frac(rows,ls,min(end,ls+70000)); b=frac(rows,ss,min(end,ss+55000)); c=frac(rows,ss+55000,end)
    print(n, 'dead' if dead else 'alive', '%d/%d'%a, '%d/%d=%.0f%%'%(b[0],b[1],100*b[0]/max(b[1],1)), '%d/%d'%c, 'S-L gap s=%.0f'%((ss-ls)/1000))
