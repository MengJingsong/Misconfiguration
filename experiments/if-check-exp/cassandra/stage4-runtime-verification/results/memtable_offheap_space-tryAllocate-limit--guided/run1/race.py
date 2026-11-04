import sys, re, statistics
M=1048576
for run in sys.argv[1:]:
    ev=[]
    for l in open(f'{run}/ledger.txt'):
        p=l.split(); ev.append((p[0], dict(x.split('=',1) for x in p[1:] if '=' in x)))
    t0,t1=map(int,re.search(r'T_A0=(\d+) T_A1=\d+ T_C0=\d+ T_STOP=(\d+)', open(f'{run}/summary.txt').read()).groups())
    live={}; life=[]; L=0; maxL=0; maxi=0; racefate=set(); born={}
    for i,(k,f) in enumerate(ev):
        if k=='malloc': live[f['peer']]=i; born[i]=int(f['ms']); L+=int(f['cap'])
        elif k=='free':
            j=live.pop(f['peer']); L-=int(f['cap'])
            if f['site']=='race': racefate.add(j); life.append(int(f['ms'])-born[j])
        ms=int(f['ms'])
        if t0<=ms<=t1 and L>maxL: maxL,maxi=L,i
    # race-fated regions live at the peak
    live={}; 
    for i,(k,f) in enumerate(ev[:maxi+1]):
        if k=='malloc': live[f['peer']]=(i,int(f['cap']))
        elif k=='free': live.pop(f['peer'],None)
    rl=[c for p,(j,c) in live.items() if j in racefate]
    print(f'{run}: race frees {len(life)}, lifetime ms median {statistics.median(life) if life else None} max {max(life) if life else None}; '
          f'race-fated regions live at max L: {len(rl)} = {sum(rl)/M:.2f} MiB')
