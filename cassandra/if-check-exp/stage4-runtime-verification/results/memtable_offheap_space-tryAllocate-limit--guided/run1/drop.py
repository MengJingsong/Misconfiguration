import sys, bisect
M=1048576
for run in sys.argv[1:]:
    rows=[tuple(int(x) for x in l.split(',')) for l in open(f'{run}/rss.csv').read().splitlines()[1:] if l.strip()]
    ts=[r[0] for r in rows]
    big=[]
    for l in open(f'{run}/ledger.txt'):
        if l.startswith('discard '):
            kv=dict(x.split('=',1) for x in l.split()[1:]); 
            if int(kv['owns'])>=64*M: big.append((int(kv['ms']),int(kv['owns'])))
    out=[]
    for ms,own in big[:6]:
        i=bisect.bisect_left(ts,ms)
        before=rows[max(i-1,0)][1]; after=rows[min(i+1,len(rows)-1)][1]
        out.append(f'{own/M:.0f}MiB: dRss {(after-before)/1024:+.0f}MiB')
    print(run, '|', '; '.join(out))
