#!/usr/bin/env python3
"""B3a node configuration for case o100 (amendment S4-A1). Usage: mkconf.py <tree> <run>
Directories under <run>; 127.0.0.1; seeds 127.0.0.1:7000; concurrent_writes 4; commitlog_sync periodic 1000ms;
memtable_heap_space 2048MiB. Default ports 7000/7199/9042. Idempotent (replaces its own block)."""
import re, sys
tree, run = sys.argv[1], sys.argv[2]
yml = f"{tree}/conf/cassandra.yaml"
t = open(yml).read()
MARK = "# --- o100 stage-4 settings ---"
t = t.split("\n" + MARK)[0]
def drop(key):
    global t
    t = re.sub(rf"(?m)^{key}:.*\n(?:[ \t-].*\n)*", "", t)
for k in ["data_file_directories", "commitlog_directory", "hints_directory", "saved_caches_directory", "cdc_raw_directory",
          "listen_address", "rpc_address", "seed_provider", "concurrent_writes", "commitlog_sync", "commitlog_sync_period",
          "memtable_heap_space"]:
    drop(k)
t = t.rstrip("\n") + f"""
{MARK}
data_file_directories:
    - {run}/data
commitlog_directory: {run}/commitlog
hints_directory: {run}/hints
saved_caches_directory: {run}/saved_caches
cdc_raw_directory: {run}/cdc_raw
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "127.0.0.1:7000"
concurrent_writes: 4
commitlog_sync: periodic
commitlog_sync_period: 1000ms
memtable_heap_space: 2048MiB
"""
open(yml, "w").write(t)
print(f"mkconf: {yml} updated for run dir {run}")
