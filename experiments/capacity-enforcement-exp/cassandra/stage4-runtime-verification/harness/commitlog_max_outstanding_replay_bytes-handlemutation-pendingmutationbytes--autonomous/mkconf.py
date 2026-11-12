#!/usr/bin/env python3
"""Configure the node tree for case o32 (B3a with amendments M1-M3).
Usage: mkconf.py <tree> <nodedir> load|replay [bytes count]
  load:   commitlog_total_space 4096MiB, memtable_heap_space 3072MiB, concurrent_writes 32
  replay: memtable_heap_space 256MiB, concurrent_writes 2 (M2); jvm-server.options gets the two -D lines
Both phases: heap_buffers, memtable_cleanup_threshold 0.99 (M3), segment size 32MiB (default),
127.0.0.1, storage 7300, ssl 7301, native 9342, JMX 7499 (M1), all directories under <nodedir>."""
import re, sys
tree, nodedir, phase = sys.argv[1], sys.argv[2], sys.argv[3]
yml = f"{tree}/conf/cassandra.yaml"
t = open(yml).read()
MARK = "# --- o32 stage-4 settings ---"
t = t.split("\n" + MARK)[0]
def drop(key):
    global t
    t = re.sub(rf"(?m)^{key}:.*\n(?:[ \t-].*\n)*", "", t)
for k in ["cluster_name", "data_file_directories", "commitlog_directory", "hints_directory",
          "saved_caches_directory", "cdc_raw_directory", "listen_address", "rpc_address", "storage_port",
          "ssl_storage_port", "native_transport_port", "commitlog_total_space", "memtable_heap_space",
          "memtable_allocation_type", "memtable_cleanup_threshold", "concurrent_writes", "seed_provider",
          "commitlog_segment_size"]:
    drop(k)
mem = "3072MiB" if phase == "load" else "256MiB"
cw = 32 if phase == "load" else 2
t += f"""
{MARK}
cluster_name: 'o32'
data_file_directories:
    - {nodedir}/data
commitlog_directory: {nodedir}/commitlog
hints_directory: {nodedir}/hints
saved_caches_directory: {nodedir}/saved_caches
cdc_raw_directory: {nodedir}/cdc_raw
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
storage_port: 7300
ssl_storage_port: 7301
native_transport_port: 9342
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "127.0.0.1:7300"
commitlog_segment_size: 32MiB
commitlog_total_space: 4096MiB
memtable_heap_space: {mem}
memtable_allocation_type: heap_buffers
memtable_cleanup_threshold: 0.99
concurrent_writes: {cw}
"""
open(yml, "w").write(t)
env = f"{tree}/conf/cassandra-env.sh"
e = open(env).read()
e = re.sub(r'(?m)^JMX_PORT="\d+"', 'JMX_PORT="7499"', e)
open(env, "w").write(e)
opt = f"{tree}/conf/jvm-server.options"
o = open(opt).read().split("\n" + MARK)[0].rstrip("\n") + "\n"
if phase == "replay":
    b, c = sys.argv[4], sys.argv[5]
    o += f"{MARK}\n-Dcassandra.commitlog_max_outstanding_replay_count={c}\n-Dcassandra.commitlog_max_outstanding_replay_bytes={b}\n"
open(opt, "w").write(o)
print(f"mkconf phase={phase} memtable_heap_space={mem} concurrent_writes={cw} " + (f"bytes={sys.argv[4]} count={sys.argv[5]}" if phase == "replay" else ""))
