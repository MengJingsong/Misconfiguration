#!/usr/bin/env python3
"""R13 (from B14): read `jcmd <pid> Thread.print` on stdin; print one line:
ntr bm getmut wait clog memt decode verify
ntr = Native-Transport-Requests threads; bm = of those, with a BatchMessage.execute frame (held batch requests on NTR);
getmut / wait / clog / memt = of bm, the top-most matching frame is in getMutations/addUpdates/collector, in
StorageProxy/AbstractWriteResponseHandler (waiting for the write), in CommitLog.add, in Memtable put;
decode = threads (any) with a BatchMessage$1.decode frame (event-loop decode);
verify = of bm, with a verifyBatchSize frame (the batch check, incl. its ERROR logging)."""
import sys
blocks = sys.stdin.read().split('\n\n')
ntr = bm = gm = wt = cl = mt = dec = ver = 0
for b in blocks:
    if 'BatchMessage$1.decode' in b: dec += 1
    if not b.startswith('"Native-Transport-Requests'): continue
    ntr += 1
    if 'BatchMessage.execute' not in b: continue
    bm += 1
    if 'verifyBatchSize' in b: ver += 1
    for line in b.splitlines():
        line = line.strip()
        if not line.startswith('at '): continue
        if 'CommitLog.add' in line: cl += 1; break
        if 'Memtable' in line and ('.put' in line or 'Partition' in line): mt += 1; break
        if 'AbstractWriteResponseHandler.get' in line or 'StorageProxy.' in line: wt += 1; break
        if 'getMutations' in line or 'addUpdates' in line or 'UpdatesCollector' in line: gm += 1; break
        if 'BatchMessage.execute' in line: break
print(ntr, bm, gm, wt, cl, mt, dec, ver)
