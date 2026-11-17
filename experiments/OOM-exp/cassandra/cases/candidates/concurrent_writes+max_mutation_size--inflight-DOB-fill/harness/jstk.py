#!/usr/bin/env python3
# Classify MutationStage threads in a `jcmd <pid> Thread.print` dump (stdin): where each one is.
# Prints: total MutationStage threads, in CommitLog.add (holding the scratch DOB), of which in expandToFit /
# Mutation serialize / segment allocation wait / sync wait (finishWriteFor) / copy; and after CommitLog.add in memtable allocation wait.
import sys, re, time
txt = sys.stdin.read()
blocks = re.split(r'\n(?=")', txt)
c = dict(mut=0, cl_add=0, expand=0, serialize=0, seg_wait=0, sync_wait=0, other_in_add=0, memtable_wait=0, idle=0)
for b in blocks:
    if not b.startswith('"MutationStage'): continue
    c['mut'] += 1
    if 'CommitLog.add(' in b:
        c['cl_add'] += 1
        if 'expandToFit' in b: c['expand'] += 1
        elif 'awaitAvailableSegment' in b or 'advanceAllocatingFrom' in b: c['seg_wait'] += 1
        elif 'finishWriteFor' in b or 'maybeWaitForSync' in b or 'awaitDiskSync' in b: c['sync_wait'] += 1
        elif 'serialize' in b: c['serialize'] += 1
        else: c['other_in_add'] += 1
    elif 'MemtableAllocator' in b or 'allocate' in b and 'Memtable' in b: c['memtable_wait'] += 1
    elif 'Keyspace.apply' not in b: c['idle'] += 1
print("%d,%s" % (int(time.time() * 1000), ",".join(str(c[k]) for k in ['mut','cl_add','expand','serialize','seg_wait','sync_wait','other_in_add','memtable_wait','idle'])))
