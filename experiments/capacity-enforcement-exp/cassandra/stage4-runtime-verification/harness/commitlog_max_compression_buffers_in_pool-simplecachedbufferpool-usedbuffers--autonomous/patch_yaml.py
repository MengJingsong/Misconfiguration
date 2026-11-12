#!/usr/bin/env python3
"""Write cassandra.yaml for one cluster-tier configuration (B3a as amended by M4/M5).
usage: patch_yaml.py <orig cassandra.yaml> <out> <cfg> <data-dir>
cfg: N3 | N6 | N12 (Zstd-19) | C1 (LZ4, N=12) | C2 (no compression, N=3) | N1 (Zstd-19, N=1)
Every top-level key set below is first removed from the original (with its indented block), then the block is appended,
so no key appears twice. The seed's port follows storage_port."""
import re
import sys

orig, out, cfg, data = sys.argv[1:5]
N = {"N3": 3, "N6": 6, "N12": 12, "C1": 12, "C2": 3, "N1": 1}[cfg]
comp = {"C1": "  - class_name: LZ4Compressor\n", "C2": None}.get(
    cfg, "  - class_name: ZstdCompressor\n    parameters:\n      - compression_level: \"19\"\n")

block = f"""
# ---- stage-4 o45 overrides ({cfg}) ----
data_file_directories:
  - {data}/data
commitlog_directory: {data}/commitlog
hints_directory: {data}/hints
saved_caches_directory: {data}/saved_caches
cdc_raw_directory: {data}/cdc_raw
commitlog_segment_size: 64MiB
""" + (f"commitlog_compression:\n{comp}" if comp else "") + f"""commitlog_disk_access_mode: legacy
commitlog_sync: periodic
commitlog_sync_period: 10000ms
commitlog_total_space: 8192MiB
file_cache_size: 64MiB
networking_cache_size: 64MiB
commitlog_max_compression_buffers_in_pool: {N}
periodic_commitlog_sync_lag_block: 600000ms
write_request_timeout: 600000ms
native_transport_timeout: 600000ms
storage_port: 7300
ssl_storage_port: 7301
native_transport_port: 9342
"""
keys = set(re.findall(r"^([a-z_]+):", block, re.M))
lines = open(orig).read().split("\n")
res, skip = [], False
for ln in lines:
    m = re.match(r"^([a-z_]+):", ln)
    if m:
        skip = m.group(1) in keys
    elif ln and not ln[0].isspace() and not ln.startswith("-"):
        skip = False  # a comment or other top-level text ends a skipped block
    if not skip:
        res.append(ln)
text = "\n".join(res)
text, k = re.subn(r'(- seeds: ")127\.0\.0\.1:7000(")', r"\g<1>127.0.0.1:7300\g<2>", text)
if k != 1:
    raise SystemExit("seeds line not found")
open(out, "w").write(text + block)
origtext = "\n".join(lines)
present = sorted(kk for kk in keys if re.search("^" + kk + ":", origtext, re.M))
cname = "none" if comp is None else comp.split(":")[1].split()[0]
print("wrote %s for %s: N=%d, compression=%s; replaced keys present in orig: %s" % (out, cfg, N, cname, ",".join(present)))
