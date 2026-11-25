#!/bin/bash
# o125 cluster tier setup (B3a, with S4-A1). Runs ON the node. Logs every command and its output.
set -uo pipefail
WORK=/mydata/jingsong-cass-s4/o125
H=$WORK/harness
LOG=$WORK/logs
mkdir -p $LOG
exec > >(tee -a $LOG/cluster-setup.log) 2>&1
set -x
date -u
# S4-A4(b): the unit tier's copy is removed before the cluster copy
rm -rf $WORK/src; df -h /mydata
[ -d $WORK/cass ] || cp -a /mydata/s4/cassandra-base $WORK/cass || exit 1
F=$WORK/cass/src/java/org/apache/cassandra/net/OutboundConnectionSettings.java
python3 - "$F" "$H/patch-line103.txt" <<'EOF' || exit 1
import sys
f, p = sys.argv[1], sys.argv[2]
lines = open(f).read().split('\n')
stock = "        this(null, to, preferred, null, null, null, null, null, null, null, 1 << 15, 1 << 16, null, null, null, null, null, null, null, null);"
# defect fix #2: the stock line is line 104 at cassandra-5.0.9 (B3a said 103); patch the one line that holds it
idx = [i for i, l in enumerate(lines) if l == stock]
if len(idx) == 1:
    i = idx[0]
    lines[i:i+1] = open(p).read().rstrip('\n').split('\n')
    open(f, 'w').write('\n'.join(lines))
    print("patched line %d" % (i + 1))
elif any('cassandra.test.flush_high_water_mark' in l for l in lines):
    print("already patched")
else:
    print("stock line not found exactly once: %d" % len(idx)); sys.exit(1)
EOF
sed -n 98,110p $F
cd $WORK/cass && ant -Dno-checkstyle=true jar </dev/null > $LOG/cluster-ant-jar.log 2>&1; echo "ant jar exit $?"; tail -3 $LOG/cluster-ant-jar.log
unzip -p $WORK/cass/build/apache-cassandra-5.0.9-SNAPSHOT.jar org/apache/cassandra/net/OutboundConnectionSettings.class | strings | grep -c 'cassandra.test.flush_'
for X in A B; do
  rm -rf $WORK/conf$X; cp -a $WORK/cass/conf $WORK/conf$X
  if [ $X = A ]; then IP=127.0.0.1; else IP=127.0.0.2; fi
  python3 - "$WORK/conf$X/cassandra.yaml" "$IP" "$WORK/node$X" <<'EOF' || exit 1
import sys, re
f, ip, d = sys.argv[1:4]
ov = {
 'cluster_name': 'fhwm', 'num_tokens': '16', 'listen_address': ip, 'rpc_address': ip,
 'commitlog_directory': d + '/commitlog', 'saved_caches_directory': d + '/saved_caches',
 'hints_directory': d + '/hints', 'cdc_raw_directory': d + '/cdc_raw',
 'hinted_handoff_enabled': 'false', 'phi_convict_threshold': '12', 'write_request_timeout': '10000ms',
 'internode_compression': 'none', 'internode_socket_send_buffer_size': '4KiB',
 'internode_socket_receive_buffer_size': '4KiB', 'internode_tcp_user_timeout': '0ms',
 'networking_cache_size': '128MiB'}
out = []
for l in open(f).read().split('\n'):
    k = l.split(':', 1)[0]
    if k in ov or k == 'data_file_directories':
        out.append('# (o125 override) ' + l); continue
    out.append(l)
out.append('# ---- o125 stage-4 overrides (B3a) ----')
for k, v in ov.items():
    out.append('%s: %s' % (k, v))
out.append('data_file_directories:\n    - %s/data' % d)
open(f, 'w').write('\n'.join(out) + '\n')
EOF
  grep -n 'seeds:' $WORK/conf$X/cassandra.yaml
  sed -n '/o125 stage-4 overrides/,$p' $WORK/conf$X/cassandra.yaml
done
sed -i 's/^JMX_PORT="7199"/JMX_PORT="7299"/' $WORK/confB/cassandra-env.sh
grep -n '^JMX_PORT=' $WORK/confA/cassandra-env.sh $WORK/confB/cassandra-env.sh
# Sampler parse check (single-file source launch compiles it)
mkdir -p $WORK/samplerchk && cp $H/Sampler.java $WORK/samplerchk/ && (cd $WORK/samplerchk && javac Sampler.java && echo "Sampler compiles") ; rm -rf $WORK/samplerchk
date -u
