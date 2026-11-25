#!/usr/bin/env python3
# R23 gate G2 reader for one jcmd Thread.print file: flush-writer threads (names containing MemtableFlushWriter, which
# includes 5.0's PerDiskMemtableFlushWriter_*) with a flush-I/O frame (force/fsync/write/open0), MutationStage threads
# total and parked in MemtableAllocator$SubAllocator.allocate, and main's top Cassandra frame.
import re, sys
IO = re.compile(r'FileChannelImpl\.force|FileDispatcherImpl\.force|fsync|FileDispatcherImpl\.(p?write)|FileChannelImpl\.write|open0|SyncUtil\.force')
blocks = re.split(r'\n(?=")', open(sys.argv[1], errors='replace').read())
fw = fw_io = ms = ms_sub = 0; main = '-'
for b in blocks:
    name = b.split('"')[1] if b.startswith('"') else ''
    if 'MemtableFlushWriter' in name:
        fw += 1; fw_io += bool(IO.search(b))
    elif name.startswith('MutationStage'):
        ms += 1; ms_sub += 'SubAllocator.allocate' in b
    elif name == 'main':
        fr = [l.strip()[3:] for l in b.splitlines() if l.strip().startswith('at ') and 'cassandra' in l]
        main = fr[0].split('(')[0] if fr else '-'
g2 = 'G2=yes' if fw_io >= 1 and ms_sub >= 24 else ('G2C=yes' if fw_io >= 1 else 'G2=no')
print(f'flushwriters={fw} flushwriters_in_io={fw_io} mutstage={ms} mutstage_in_suballoc={ms_sub} main={main} {g2}')
