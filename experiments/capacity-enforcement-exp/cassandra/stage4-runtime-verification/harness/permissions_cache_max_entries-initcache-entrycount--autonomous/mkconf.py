# Write an arm's cassandra.yaml from the pristine copy (B3a + AM1/AM2). usage: mkconf.py <orig> <out> <nodedir> <M> <validity_ms>
import sys, re
orig, out, nd, M, val = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
repl = {'authenticator': 'PasswordAuthenticator', 'authorizer': 'CassandraAuthorizer', 'permissions_validity': f'{val}ms',
        'storage_port': '7300', 'ssl_storage_port': '7301', 'native_transport_port': '9342',
        'listen_address': '127.0.0.1', 'rpc_address': '127.0.0.1'}
lines, seen = [], set()
for line in open(orig):
    m = re.match(r'^([a-z_]+):\s', line)
    if m and m.group(1) in repl:
        line = f'{m.group(1)}: {repl[m.group(1)]}\n'; seen.add(m.group(1))
    if re.match(r'^\s+- seeds: "127\.0\.0\.1:7000"', line):
        line = line.replace('127.0.0.1:7000', '127.0.0.1:7300'); seen.add('seeds')
    lines.append(line)
missing = set(repl) | {'seeds'}; missing -= seen
assert not missing, missing
for k in ('permissions_update_interval', 'permissions_cache_max_entries', 'data_file_directories', 'commitlog_directory',
          'saved_caches_directory', 'hints_directory', 'cdc_raw_directory'):
    assert not any(l.startswith(k + ':') for l in lines), k
lines.append(f"""
# --- stage-4 o03 arm overrides (B3a, B3b, AM1, AM2)
permissions_update_interval: 3600000ms
permissions_cache_max_entries: {M}
data_file_directories:
  - {nd}/data
commitlog_directory: {nd}/commitlog
saved_caches_directory: {nd}/saved_caches
hints_directory: {nd}/hints
cdc_raw_directory: {nd}/cdc_raw
""")
open(out, 'w').writelines(lines)
