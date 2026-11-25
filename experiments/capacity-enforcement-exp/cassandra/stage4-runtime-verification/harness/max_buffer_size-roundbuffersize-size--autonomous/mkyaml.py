# Amendment A4: write conf/cassandra.yaml from the pristine .orig, setting exactly the B3a keys (paths per A1).
# usage: mkyaml.py <orig> <out> <node_dir>
import re, sys
orig, out, nd = sys.argv[1], sys.argv[2], sys.argv[3]
keys = {
 'cluster_name': "s3probe",
 'data_file_directories': "\n    - %s/data" % nd,
 'commitlog_directory': "%s/commitlog" % nd,
 'saved_caches_directory': "%s/saved_caches" % nd,
 'hints_directory': "%s/hints" % nd,
 'commitlog_total_space': "1024MiB",
 'listen_address': "127.0.0.1",
 'rpc_address': "127.0.0.1",
 'seed_provider': "\n  - class_name: org.apache.cassandra.locator.SimpleSeedProvider\n    parameters:\n      - seeds: \"127.0.0.1:7000\"",
 'disk_access_mode': "mmap_index_only",
 'file_cache_enabled': "false",
 'disk_optimization_strategy': "ssd",
 'compaction_throughput': "1MiB/s",
}
lines = open(orig).read().split('\n')
res, skip, removed = [], False, []
for l in lines:
    m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):', l)
    if m:
        skip = m.group(1) in keys
        if skip: removed.append(m.group(1)); continue
    elif skip and (l.startswith((' ', '\t', '-'))):
        continue
    else:
        skip = False
    res.append(l)
res.append('\n# --- s3probe (case B3a, amendment A4) ---')
for k, v in keys.items():
    res.append('%s: %s' % (k, v) if not v.startswith('\n') else '%s:%s' % (k, v))
open(out, 'w').write('\n'.join(res) + '\n')
try:
    import yaml
    y = yaml.safe_load(open(out))
    for k in keys:
        print('yaml-check', k, '=', y[k])
except ImportError:
    print('yaml-check skipped (no PyYAML)')
print('replaced top-level keys:', removed)
