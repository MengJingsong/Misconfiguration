#!/usr/bin/env python3
"""Independent recount of one thread dump (results §5.1). Different method from the run script's awk: it splits the dump into
per-thread blocks and classifies each by its own frames. Usage: recount.py <dump file>"""
import sys, re
txt = open(sys.argv[1]).read()
blocks = [b for b in re.split(r'\n\s*\n', txt) if b.startswith('"')]
parked = blocked = other = 0
ms_states = {}
for b in blocks:
    name = b.split('"')[1]
    st = re.search(r'java\.lang\.Thread\.State: (\S+(?: \([^)]*\))?)', b)
    st = st.group(1) if st else '?'
    if name.startswith('MutationStage'):
        ms_states[st] = ms_states.get(st, 0) + 1
    if 'HintsBufferPool.switchCurrentBuffer' not in b:
        continue
    if 'LinkedBlockingQueue.take' in b and 'HintsBufferPool.switchCurrentBuffer(HintsBufferPool.java:118)' in b:
        parked += 1
    elif 'waiting to lock' in b and '(a org.apache.cassandra.hints.HintsBufferPool)' in b and 'HintsBufferPool.switchCurrentBuffer(HintsBufferPool.java:109)' in b:
        blocked += 1
    else:
        other += 1
print(f"threads={len(blocks)} parked_at_118={parked} blocked_at_109={blocked} other_in_switchCurrentBuffer={other} MutationStage_states={dict(sorted(ms_states.items()))}")
