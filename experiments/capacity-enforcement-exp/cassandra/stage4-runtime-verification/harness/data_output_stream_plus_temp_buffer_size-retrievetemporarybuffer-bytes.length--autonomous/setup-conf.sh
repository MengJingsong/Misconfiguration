#!/bin/bash
# B3a as amended by A2: edit the copy's conf (never the repository source). Idempotent.
set -euo pipefail
WORK=/mydata/jingsong-cass-s4/o43; Y=$WORK/src/conf/cassandra.yaml; E=$WORK/src/conf/cassandra-env.sh
[ -f $Y.orig ] || cp $Y $Y.orig; [ -f $E.orig ] || cp $E $E.orig
cp $Y.orig $Y; cp $E.orig $E
python3 - "$Y" "$WORK" <<'PY'
import sys, re
y, w = sys.argv[1], sys.argv[2]
t = open(y).read()
def sub(pat, rep):
    global t
    t2, n = re.subn(pat, rep, t, count=1, flags=re.M)
    assert n == 1, pat
    t = t2
sub(r'^# data_file_directories:\n#     - /var/lib/cassandra/data', f'data_file_directories:\n    - {w}/node/data')
sub(r'^# commitlog_directory: .*$', f'commitlog_directory: {w}/node/commitlog')
sub(r'^# hints_directory: .*$', f'hints_directory: {w}/node/hints')
sub(r'^# saved_caches_directory: .*$', f'saved_caches_directory: {w}/node/saved_caches')
sub(r'^# cdc_raw_directory: .*$', f'cdc_raw_directory: {w}/node/cdc')
sub(r'^memtable_allocation_type: .*$', 'memtable_allocation_type: offheap_buffers')
sub(r'^# memtable_heap_space: .*$', 'memtable_heap_space: 1024MiB')
sub(r'^# memtable_offheap_space: .*$', 'memtable_offheap_space: 2048MiB')
sub(r'^# row_cache_class_name: .*$', 'row_cache_class_name: org.apache.cassandra.cache.SerializingCacheProvider')
sub(r'^row_cache_size: .*$', 'row_cache_size: 1024MiB')
sub(r'^row_cache_save_period: .*$', 'row_cache_save_period: 0s')
sub(r'^storage_port: .*$', 'storage_port: 7300')
sub(r'^ssl_storage_port: .*$', 'ssl_storage_port: 7301')
sub(r'^native_transport_port: .*$', 'native_transport_port: 9342')
sub(r'^listen_address: .*$', 'listen_address: 127.0.0.1')
sub(r'^rpc_address: .*$', 'rpc_address: 127.0.0.1')
sub(r'- seeds: "127.0.0.1:7000"', '- seeds: "127.0.0.1:7300"')
open(y, 'w').write(t)
PY
sed -i 's/^JMX_PORT="7199"/JMX_PORT="7499"/' $E
grep -q '^JMX_PORT="7499"' $E
diff $Y.orig $Y || true
diff $E.orig $E || true
