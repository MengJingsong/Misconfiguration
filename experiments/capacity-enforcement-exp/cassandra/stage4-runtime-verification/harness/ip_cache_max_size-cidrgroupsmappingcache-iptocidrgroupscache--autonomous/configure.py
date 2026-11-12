#!/usr/bin/env python3
"""B3a edits (with AM1/AM2) to the copy's conf/cassandra.yaml and conf/cassandra-env.sh.
Usage: configure.py <src-dir> <K> <data-dir>. Run on a pristine conf (git checkout -- conf first)."""
import re, sys
src, K, data = sys.argv[1], sys.argv[2], sys.argv[3]
y = open(f'{src}/conf/cassandra.yaml').read()
def sub(pat, rep, s, count=1):
    n = len(re.findall(pat, s, flags=re.M))
    assert n == count, (pat, n)
    return re.sub(pat, rep, s, flags=re.M)
y = sub(r'^authenticator: AllowAllAuthenticator$', 'authenticator: PasswordAuthenticator', y)
block = ('cidr_authorizer:\n  class_name: CassandraCIDRAuthorizer\n  parameters:\n'
         '    cidr_authorizer_mode: "MONITOR"\n    cidr_groups_cache_refresh_interval: "1440"\n'
         f'    ip_cache_max_size: "{K}"\n')
y = sub(r'^cidr_authorizer:\n  class_name: AllowAllCIDRAuthorizer\n', block, y)
y = sub(r'^# data_file_directories:\n', f'data_file_directories:\n    - {data}/data\n', y)
y = sub(r'^# commitlog_directory: .*$', f'commitlog_directory: {data}/commitlog', y)
y = sub(r'^# saved_caches_directory: .*$', f'saved_caches_directory: {data}/saved_caches', y)
y = sub(r'^# hints_directory: .*$', f'hints_directory: {data}/hints', y)
y = sub(r'^# cdc_raw_directory: .*$', f'cdc_raw_directory: {data}/cdc', y)
y = sub(r'^storage_port: 7000$', 'storage_port: 7300', y)
y = sub(r'^ssl_storage_port: 7001$', 'ssl_storage_port: 7301', y)
y = sub(r'^native_transport_port: 9042$', 'native_transport_port: 9342', y)
y = sub(r'^(\s+- seeds: )"127.0.0.1:7000"$', r'\1"127.0.0.1:7300"', y)
open(f'{src}/conf/cassandra.yaml', 'w').write(y)
e = open(f'{src}/conf/cassandra-env.sh').read()
e = sub(r'^JMX_PORT="7199"$', 'JMX_PORT="7499"', e)
open(f'{src}/conf/cassandra-env.sh', 'w').write(e)
print('configured K=%s' % K)
