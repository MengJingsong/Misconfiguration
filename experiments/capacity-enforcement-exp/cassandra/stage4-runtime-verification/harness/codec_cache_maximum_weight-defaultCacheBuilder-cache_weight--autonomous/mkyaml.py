#!/usr/bin/env python3
# B3a yaml edits (S4-A5) for order 96. Usage: mkyaml.py <node-dir> <data-root> [cluster_name]
# Edits <node-dir>/conf/cassandra.yaml in place, starting from a pristine copy kept as cassandra.yaml.orig.
import os, shutil, sys, yaml
node, data = sys.argv[1], sys.argv[2]
name = sys.argv[3] if len(sys.argv) > 3 else 'codec96'
y = os.path.join(node, 'conf', 'cassandra.yaml')
orig = y + '.orig'
if not os.path.exists(orig):
    shutil.copy(y, orig)
c = yaml.safe_load(open(orig))
c.update({
    'cluster_name': name,
    'user_defined_functions_enabled': True,
    'data_file_directories': [os.path.join(data, 'data')],
    'commitlog_directory': os.path.join(data, 'commitlog'),
    'hints_directory': os.path.join(data, 'hints'),
    'saved_caches_directory': os.path.join(data, 'saved_caches'),
    'cdc_raw_directory': os.path.join(data, 'cdc'),
    'listen_address': '127.0.0.1',
    'rpc_address': '127.0.0.1',
})
c['seed_provider'][0]['parameters'][0]['seeds'] = '127.0.0.1:7000'
yaml.safe_dump(c, open(y, 'w'), default_flow_style=False, sort_keys=False)
for k in ('cluster_name', 'user_defined_functions_enabled', 'data_file_directories', 'commitlog_directory',
          'hints_directory', 'saved_caches_directory', 'cdc_raw_directory', 'listen_address', 'rpc_address'):
    print(k, '=', c[k])
