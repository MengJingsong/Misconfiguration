#!/usr/bin/env python3
# B3c statement generator (S4-A6) for order 96. Usage: gen-cql.py <out-dir>
import os, sys
d = sys.argv[1]
os.makedirs(d, exist_ok=True)

def w(name, lines):
    with open(os.path.join(d, name), 'w') as f:
        f.write('\n'.join(lines) + '\n')

def narrow(i):
    return f"CREATE FUNCTION ks.f_{i}(v vector<int, {i}>) CALLED ON NULL INPUT RETURNS int LANGUAGE java AS 'return 1;';"

def wide(prefix, m, i):
    comps = ', '.join(['int'] * m + [f'vector<int, {i}>'])
    return f"CREATE FUNCTION ks.{prefix}_{i}(t tuple<{comps}>) CALLED ON NULL INPUT RETURNS int LANGUAGE java AS 'return 1;';"

w('narrow_1_500.cql', [narrow(i) for i in range(1, 501)])
w('narrow_501_2000.cql', [narrow(i) for i in range(501, 2001)])
w('narrow_2001_4000.cql', [narrow(i) for i in range(2001, 4001)])
w('narrow_drop.cql', [f"DROP FUNCTION ks.f_{i};" for i in range(1, 4001)])
w('wide_m1.cql', [wide('g', 1, i) for i in range(1, 1501)])
w('wide_m1_drop.cql', [f"DROP FUNCTION ks.g_{i};" for i in range(1, 1501)])
w('wide_m2000.cql', [wide('h', 2000, i) for i in range(1, 1501)])
w('wide_m2000_drop.cql', [f"DROP FUNCTION ks.h_{i};" for i in range(1, 1501)])
# shakedown (instrument check only, separate throwaway node): 3 narrow, 2 wide M=2000
w('shake.cql', ["CREATE KEYSPACE IF NOT EXISTS ks WITH replication={'class':'SimpleStrategy','replication_factor':1};"]
  + [f"CREATE FUNCTION ks.s_{i}(v vector<int, {i}>) CALLED ON NULL INPUT RETURNS int LANGUAGE java AS 'return 1;';" for i in range(1, 4)]
  + [wide('sw', 2000, i) for i in range(1, 3)]
  + ["SELECT count(*) FROM system_schema.functions WHERE keyspace_name='ks';"])
for f in sorted(os.listdir(d)):
    p = os.path.join(d, f)
    print(f, sum(1 for _ in open(p)), 'lines', os.path.getsize(p), 'bytes')
