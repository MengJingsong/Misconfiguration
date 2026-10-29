#!/usr/bin/env bash
# usage: make-node.sh <appender on|off> [copy dir]   (case B3a, 2026-10-28)
# Builds $T/conf (T=~/stage4-tmp/lv/node) from the run copy's conf/: the tag's cassandra.yaml with one node on 127.0.0.1 and every directory under $T (local disk);
# G1 flags removed from jvm11-server.options and -XX:+UseSerialGC added (B3a: -XX:+UseSerialGC); logback.xml: with `on`, the CQLLOG appender and its appender-ref are
# uncommented, its ThresholdFilter is TRACE and the org.apache.cassandra logger is TRACE (B3a). The run copy's conf/ is not changed.
set -euo pipefail
mode=${1:?on|off}; C=${2:-$HOME/s4-lv}; T=${T:-$HOME/stage4-tmp/lv/node}
mkdir -p "$T/logs" "$T/data" "$T/commitlog" "$T/hints" "$T/saved_caches" "$T/cdc_raw"
rm -rf "$T/conf"; cp -r "$C/conf" "$T/conf"
git -C "$C" show HEAD:conf/cassandra.yaml > "$T/shipped.yaml"
cat > "$T/lines.yaml" <<EOL
cluster_name: stage4-lv
num_tokens: 1
endpoint_snitch: SimpleSnitch
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "127.0.0.1:7000"
data_file_directories:
    - $T/data
commitlog_directory: $T/commitlog
hints_directory: $T/hints
saved_caches_directory: $T/saved_caches
cdc_raw_directory: $T/cdc_raw
commitlog_total_space: 2GiB
EOL
python3 - "$T" "$mode" <<'PY'
import re, sys
n, mode = sys.argv[1:3]
add = open(n + '/lines.yaml').read().splitlines()
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
out, skip = [], False
for l in open(n + '/shipped.yaml').read().splitlines():
    m = re.match(r'^([A-Za-z_]+):', l)
    if m:
        skip = m.group(1) in keys
        if skip: continue
    elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
        continue
    else:
        skip = False
    out.append(l)
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 lv lines ----\n' + '\n'.join(add) + '\n')
# JVM options: SerialGC instead of G1
jo = open(n + '/conf/jvm11-server.options').read().splitlines()
jo = [l for l in jo if not re.search(r'G1|MaxGCPauseMillis|InitiatingHeapOccupancy|UnlockExperimentalVMOptions|ParallelRefProc', l) or l.startswith('#')]
open(n + '/conf/jvm11-server.options', 'w').write('\n'.join(jo) + '\n-XX:+UseSerialGC\n')
if mode == 'on':
    x = open(n + '/conf/logback.xml').read()
    a = x.replace('<!-- <appender name="CQLLOG"', '<appender name="CQLLOG"').replace('</appender> -->\n\n  <root', '</appender>\n\n  <root')
    a = a.replace('<level>WARN</level>\n    </filter>\n  </appender>\n\n  <root', '<level>TRACE</level>\n    </filter>\n  </appender>\n\n  <root')
    a = a.replace('<!--\n    <appender-ref ref="CQLLOG"/>\n    -->', '<appender-ref ref="CQLLOG"/>')
    a = a.replace('<logger name="org.apache.cassandra" level="DEBUG"/>', '<logger name="org.apache.cassandra" level="TRACE"/>')
    assert a.count('CQLLOG') == 2 and 'level="TRACE"' in a and '<level>TRACE</level>' in a, 'logback edit failed'
    open(n + '/conf/logback.xml', 'w').write(a)
PY
echo "node conf $T/conf: appender $mode"
