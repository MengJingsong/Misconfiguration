#!/usr/bin/env python3
"""Readings summary for o124 cluster tier (B3f): dU = peak paused UsedSize - baseline UsedSize; B_k = srvSendQ + proxyRecvQ
at that sample (summed over connections); R = K * 8,388,617."""
import sys, re
def parse(path):
    samples=[]; cur=None
    for line in open(path):
        line=line.rstrip('\n')
        m=re.match(r'== (\S+) (\S+)', line)
        if m: cur={'tag':m.group(1),'t':float(m.group(2)),'srv':0,'prx':0}; samples.append(cur); continue
        if cur is None: continue
        f=line.split()
        if len(f)==2 and f[0] in ('UsedSize','Size','OverflowSize') and f[1].lstrip('-').isdigit(): cur[f[0]]=int(f[1])
        elif len(f)==2 and f[0]=='srvSendQ' and f[1].isdigit(): cur['srv']+=int(f[1])
        elif len(f)==2 and f[0]=='proxyRecvQ' and f[1].isdigit(): cur['prx']+=int(f[1])
        elif 'Other (' in line:
            cur['nmt_other_kb']=int(re.search(r'committed=(\d+)KB',line).group(1))
    return samples
for path in sys.argv[1:]:
    K=int(re.search(r'K(\d)',path).group(1)) if re.search(r'-K(\d)',path) else 8
    s=parse(path); base=s[0]; paused=[x for x in s if x['tag'].startswith('paused')]; rel=[x for x in s if x['tag']=='released'][0]
    peak=max(paused,key=lambda x:x['UsedSize']); dU=peak['UsedSize']-base['UsedSize']; Bk=peak['srv']+peak['prx']; R=K*8388617
    used=[x['UsedSize'] for x in paused]
    print(f"{path}: K={K} baseUsed={base['UsedSize']} peakUsed={peak['UsedSize']} dU={dU} Bk={Bk} (srv {peak['srv']} + proxy {peak['prx']}) R={R} R-Bk={R-Bk} dU/(R-Bk)={dU/(R-Bk):.4f}"
          f" plateau min/max={min(used)}/{max(used)} spread={(max(used)-min(used))/max(dU,1):.4%}"
          f" pooled(Size-Overflow) base/peak/max={base['Size']-base['OverflowSize']}/{peak['Size']-peak['OverflowSize']}/{max(x['Size']-x['OverflowSize'] for x in s)}"
          f" Overflow base/peak={base['OverflowSize']}/{peak['OverflowSize']} dOverflow={peak['OverflowSize']-base['OverflowSize']}"
          f" releasedUsed={rel['UsedSize']} (rel-base={rel['UsedSize']-base['UsedSize']})"
          f" NMTOther base/peak/rel KB={base.get('nmt_other_kb')}/{max(x.get('nmt_other_kb',0) for x in paused)}/{rel.get('nmt_other_kb')}")
