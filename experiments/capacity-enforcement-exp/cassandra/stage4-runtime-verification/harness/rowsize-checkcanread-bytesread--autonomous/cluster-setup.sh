#!/bin/bash
# Stage-4 cluster tier (B3a), one-time setup of the node tree. Runs on ms0640.
set -eu
O=/mydata/jingsong-cass-s4/o122
RUN=$O/cluster
mkdir -p $RUN
exec > >(tee -a $RUN/setup.log) 2>&1
echo "[$(date -u +%FT%TZ)] setup host=$(hostname) arch=$(uname -m)"
if [ ! -d $RUN/node-tree ]; then cp -a $O/src $RUN/node-tree; fi
cd $RUN/node-tree
git checkout -- conf/cassandra.yaml conf/cassandra-env.sh
python3 - "$RUN" <<'EOF'
import re, sys
run = sys.argv[1]
p = 'conf/cassandra.yaml'
t = open(p).read()
def setkey(t, key, val):
    pat = re.compile(r'^%s:.*$' % re.escape(key), re.M)
    if pat.search(t):
        return pat.sub('%s: %s' % (key, val), t, count=1)
    return t + '\n%s: %s\n' % (key, val)
t = setkey(t, 'disk_failure_policy', 'ignore')
t = setkey(t, 'storage_port', '17100')
t = setkey(t, 'native_transport_port', '19142')
t = setkey(t, 'listen_address', '127.0.0.1')
t = setkey(t, 'rpc_address', '127.0.0.1')
t = t.replace('- seeds: "127.0.0.1:7000"', '- seeds: "127.0.0.1:17100"')
t += '\n# stage-4 o122 overrides\n'
t += 'data_file_directories:\n    - %s/data\n' % run
for k in ['commitlog', 'hints', 'saved_caches', 'cdc_raw']:
    t += '%s_directory: %s/%s\n' % (k, run, k)
t += 'max_value_size: 256MiB  # S4-MAXVALUE\n'
open(p, 'w').write(t)
import yaml
y = yaml.safe_load(open(p))
for k in ['disk_failure_policy','storage_port','native_transport_port','listen_address','rpc_address','data_file_directories',
          'commitlog_directory','hints_directory','saved_caches_directory','cdc_raw_directory','max_value_size']:
    print('YAML', k, '=', y[k])
print('YAML seeds =', y['seed_provider'][0]['parameters'][0]['seeds'])
EOF
sed -i 's/^JMX_PORT="7199"/JMX_PORT="17299"/' conf/cassandra-env.sh
grep -n '^JMX_PORT=' conf/cassandra-env.sh
git diff --stat
echo "[$(date -u +%FT%TZ)] setup done"
