#!/usr/bin/env python3
"""Cluster tier (B3a, AM3) of file_cache_size-chunk_cache_eviction-weighted_size--autonomous.
usage: python3 -I mkconf.py <src conf dir> <out conf dir> <node dir> <F MiB>
Writes cassandra.yaml, cassandra-env.sh, jvm-server.options into <out conf dir> (other files copied once)."""
import os, re, shutil, sys
src, out, node, F = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
os.makedirs(out, exist_ok=True)
for f in os.listdir(src):
    if not os.path.exists(os.path.join(out, f)) and os.path.isfile(os.path.join(src, f)):
        shutil.copy(os.path.join(src, f), out)
y = open(os.path.join(src, 'cassandra.yaml')).read()
def setk(k, v):
    global y
    pat = re.compile(r'^%s:.*$' % re.escape(k), re.M)
    assert len(pat.findall(y)) <= 1, k
    if pat.search(y):
        y = pat.sub('%s: %s' % (k, v), y)
    else:
        y += '\n%s: %s\n' % (k, v)
setk('cluster_name', "'o06'")
y = y.replace('- seeds: "127.0.0.1:7000"', '- seeds: "127.0.0.1:7400"')
assert '127.0.0.1:7400' in y
for k, v in [('listen_address', '127.0.0.1'), ('rpc_address', '127.0.0.1'), ('storage_port', '7400'), ('ssl_storage_port', '7401'),
             ('native_transport_port', '9442'), ('key_cache_size', '0MiB'), ('file_cache_enabled', 'true'),
             ('file_cache_size', '%dMiB' % F), ('disk_access_mode', 'mmap_index_only'),
             ('commitlog_directory', node + '/commitlog'), ('hints_directory', node + '/hints'),
             ('saved_caches_directory', node + '/saved_caches'), ('cdc_raw_directory', node + '/cdc_raw')]:
    setk(k, v)
y += '\ndata_file_directories:\n    - %s/data\n' % node
open(os.path.join(out, 'cassandra.yaml'), 'w').write(y)
e = open(os.path.join(src, 'cassandra-env.sh')).read()
assert e.count('JMX_PORT="7199"') == 1
e = e.replace('JMX_PORT="7199"', 'JMX_PORT="7599"')
e = e.replace('#MAX_HEAP_SIZE="20G"', 'MAX_HEAP_SIZE="2G"').replace('#HEAP_NEWSIZE="10G"', 'HEAP_NEWSIZE="400M"')
assert 'MAX_HEAP_SIZE="2G"' in e and 'HEAP_NEWSIZE="400M"' in e
open(os.path.join(out, 'cassandra-env.sh'), 'w').write(e)
j = open(os.path.join(src, 'jvm-server.options')).read()
j += '\n# stage-4 o06 (B3a)\n-XX:MaxDirectMemorySize=4G\n-XX:NativeMemoryTracking=summary\n'
open(os.path.join(out, 'jvm-server.options'), 'w').write(j)
print('conf F=%d written to %s' % (F, out))
