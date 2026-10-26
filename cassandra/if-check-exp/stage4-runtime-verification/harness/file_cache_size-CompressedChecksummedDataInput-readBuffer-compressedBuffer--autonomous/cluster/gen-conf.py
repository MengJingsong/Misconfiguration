#!/usr/bin/env python3
"""gen-conf.py <tree> <rundir> <idx> <threshold-MiB|none> <compress yes|no>  -> writes <rundir>/n<idx>/conf"""
import sys, os, re, shutil
tree, rd, idx, th, comp = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
nd = f"{rd}/n{idx}"
conf = f"{nd}/conf"
if os.path.exists(conf): shutil.rmtree(conf)
shutil.copytree(f"{tree}/conf", conf)
for d in ("data", "commitlog", "hints", "saved_caches", "cdc_raw", "logs"): os.makedirs(f"{nd}/{d}", exist_ok=True)
ip = f"127.0.12.{idx}"
y = open(f"{conf}/cassandra.yaml").read()
def setkey(key, val):
    global y
    pat = re.compile(rf"^{key}:.*$", re.M)
    if pat.search(y): y = pat.sub(f"{key}: {val}", y, count=1)
    else: y += f"\n{key}: {val}\n"
setkey("cluster_name", "'fcs'")
y = re.sub(r"^allocate_tokens_for_local_replication_factor:.*\n", "", y, flags=re.M)
setkey("num_tokens", "8")
setkey("storage_port", "7012"); setkey("native_transport_port", "9144")
setkey("listen_address", ip); setkey("rpc_address", ip)
y = y.replace('- seeds: "127.0.0.1:7000"', '- seeds: "127.0.12.1:7012"')
setkey("hinted_handoff_throttle", "30720KiB"); setkey("hints_flush_period", "1000ms")
setkey("write_request_timeout", "10000ms")
setkey("hints_directory", f"{nd}/hints"); setkey("commitlog_directory", f"{nd}/commitlog")
setkey("saved_caches_directory", f"{nd}/saved_caches"); setkey("cdc_raw_directory", f"{nd}/cdc_raw")
y += f"\ndata_file_directories:\n    - {nd}/data\n"
if idx == 1 and th != "none": y += f"\nfile_cache_size: {th}MiB\n"
if idx == 1 and comp == "yes": y += "\nhints_compression:\n  - class_name: LZ4Compressor\n"
open(f"{conf}/cassandra.yaml", "w").write(y)
env = open(f"{conf}/cassandra-env.sh").read()
env = env.replace('JMX_PORT="7199"', f'JMX_PORT="{7212 if idx == 1 else 7410 + idx}"')
open(f"{conf}/cassandra-env.sh", "w").write(env)
