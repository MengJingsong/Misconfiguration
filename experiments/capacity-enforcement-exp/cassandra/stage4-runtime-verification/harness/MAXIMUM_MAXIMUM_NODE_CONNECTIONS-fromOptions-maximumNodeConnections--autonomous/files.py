#!/usr/bin/env python3
"""files.py <data dir of keyspace k> <label> <table>
Prints one line: FILES <label> table=<t> sstables=<n> data_db=<bytes> gens=<g,...> <Component>=<bytes summed over live SSTables> ...
for every SAI per-index component of that table (file names <sstable>-SAI+<ver>+<index>+<Component>.db, Version.java:138-152),
plus per_sstable=[gen:TermsData bytes,...]. Bytes are os.stat sizes."""
import os, re, sys
from collections import defaultdict

kdir, label, table = sys.argv[1], sys.argv[2], sys.argv[3]
dirs = [d for d in os.listdir(kdir) if d.startswith(table + '-') and os.path.isdir(os.path.join(kdir, d))]
comp = defaultdict(int)
per = []
gens = []
data = 0
for d in dirs:
    p = os.path.join(kdir, d)
    for f in sorted(os.listdir(p)):
        fp = os.path.join(p, f)
        if not os.path.isfile(fp):
            continue
        if f.endswith('-Data.db') and '+' not in f:
            gens.append(f.split('-')[1]); data += os.stat(fp).st_size
        m = re.match(r'^(.*?)-SAI\+([^+]+)\+([^+]+)\+([^+.]+)\.db$', f)
        if m:
            comp[m.group(4)] += os.stat(fp).st_size
            if m.group(4) == 'TermsData':
                per.append('%s:%d' % (m.group(1).split('-')[1], os.stat(fp).st_size))
print('FILES %s table=%s dirs=%d sstables=%d data_db=%d gens=%s %s per_sstable=[%s]' % (
    label, table, len(dirs), len(gens), data, ','.join(sorted(gens)),
    ' '.join('%s=%d' % kv for kv in sorted(comp.items())), ','.join(sorted(per))))
