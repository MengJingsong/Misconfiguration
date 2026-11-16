#!/usr/bin/env python3
# S1 ledger per arm: U peak (JMX direct), K at that sample, networking pool pooled (Size-Overflow), residual U-base-K,
# heap peak, headroom vs budget, and the mean/max over samples where all 32 MutationStage threads are active.
import sys, csv, os
R=sys.argv[1]; X=float(sys.argv[2]); M=1048576.0
rows=[r for r in csv.DictReader(open(os.path.join(R,'samples.csv')))]
def f(r,k):
    try: v=float(r[k]); return v if v>=0 else None
    except: return None
good=[r for r in rows if f(r,'direct_used') is not None]
base=min(f(r,'direct_used') for r in good[:4])
pk=max(good,key=lambda r:f(r,'direct_used'))
U=f(pk,'direct_used')/M; K=(f(pk,'K_using') or 0)/M
pool=((f(pk,'net_pool_size') or 0)-(f(pk,'net_pool_overflow') or 0))/M
hp=max(f(r,'heap_used') or 0 for r in good)/M
top=sorted(f(r,'direct_used')/M for r in good)[-5:]
print("base=%.0f U_peak=%.0f K@peak=%.0f pool_pooled@peak=%.0f residual(U-base-K)=%.0f top5U=%s heap_peak=%.0f headroom=%.0f MiB (%.0f%%) samples=%d" % (
  base/M,U,K,pool,U-base/M-K,[round(x) for x in top],hp,X-U,100*(X-U)/X,len(good)))
