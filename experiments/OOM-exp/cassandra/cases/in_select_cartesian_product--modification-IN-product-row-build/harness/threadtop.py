#!/usr/bin/env python3
"""U7: read `jcmd <pid> Thread.print` on stdin; print one line:
<n NTR threads> <n NTR executing a ModificationStatement> then, per such thread, the top-most frame among
addUpdateForKey / BTreeRow$Builder.build / addUpdates / getMutations / toMutations / StorageProxy / ModificationStatement
(first matching 'at' line from the top), as name@thread-index."""
import sys
blocks = sys.stdin.read().split('\n\n')
ntr = mod = 0
tops = []
KEYS = ('addUpdateForKey', 'BTreeRow$Builder.build', 'UpdateParameters', 'addUpdates', 'getMutations', 'toMutations',
        'validateSize', 'StorageProxy', 'CommitLog', 'Memtable', 'ModificationStatement')
for b in blocks:
    if not b.startswith('"Native-Transport-Requests'): continue
    ntr += 1
    if 'ModificationStatement' not in b: continue
    mod += 1
    top = '?'
    for line in b.splitlines():
        line = line.strip()
        if not line.startswith('at '): continue
        hit = [k for k in KEYS if k in line]
        if hit:
            top = line[3:].split('(')[0].rsplit('.', 2)[-2] + '.' + line[3:].split('(')[0].rsplit('.', 1)[-1]
            break
    tops.append(top)
print(ntr, mod, ' '.join(tops) if tops else '-')
