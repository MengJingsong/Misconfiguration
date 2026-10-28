#!/usr/bin/env bash
# usage: make-node.sh <cqllog on|off> [threshold=DEBUG]       (case B3a, as amended 2026-10-27)
# Builds $T/conf (T=~/stage4-vlr/node) from the run copy's conf/: the tag's cassandra.yaml with a single node on 127.0.0.1 and
# every directory under $T on local disk, and the tag's logback.xml with the CQLLOG appender (VirtualTableAppender) uncommented
# and attached to the root logger (cqllog=on) with its ThresholdFilter at <threshold> instead of the shipped WARN, or left
# commented out as shipped (cqllog=off, the OFF arm). The DEBUGLOG rolling size is raised so debug.log stays one file.
# Nothing in the run copy is changed.
set -euo pipefail
cql=${1:?on|off}; lvl=${2:-DEBUG}
C=${CASSANDRA_HOME:-$HOME/c4-vlr}; T=${T:-$HOME/stage4-vlr/node}
mkdir -p "$T/logs" "$T/data" "$T/commitlog" "$T/hints" "$T/saved_caches" "$T/cdc_raw"
rm -rf "$T/conf"; cp -r "$C/conf" "$T/conf"
git -C "$C" show HEAD:conf/cassandra.yaml > "$T/shipped.yaml"
git -C "$C" show HEAD:conf/logback.xml > "$T/logback.shipped.xml"
cat > "$T/lines.yaml" <<EOL
cluster_name: stage4-vlr
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
EOL
python3 - "$T" "$cql" "$lvl" <<'PY'
import re, sys
n, cql, lvl = sys.argv[1:4]
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
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n# ---- stage4 vlr lines ----\n' + '\n'.join(add) + '\n')
x = open(n + '/logback.shipped.xml').read()
if cql == 'on':
    a = x.index('<!-- <appender name="CQLLOG"'); b = x.index('</appender> -->', a)
    blk = x[a:b + len('</appender> -->')]
    new = blk[len('<!-- '):-len(' -->')].replace('<level>WARN</level>', '<level>%s</level>' % lvl)
    x = x.replace(blk, new)
    ref = '<!--\n    <appender-ref ref="CQLLOG"/>\n    -->'
    assert ref in x
    x = x.replace(ref, '<appender-ref ref="CQLLOG"/>')
# keep debug.log in one file (the event counter reads it): 50MB -> 8GB per file, 5GB -> 20GB cap, DEBUGLOG appender only
i = x.index('name="DEBUGLOG"'); j = x.index('</appender>', i)
blk = x[i:j]
x = x[:i] + blk.replace('<maxFileSize>50MB</maxFileSize>', '<maxFileSize>8192MB</maxFileSize>').replace('<totalSizeCap>5GB</totalSizeCap>', '<totalSizeCap>20GB</totalSizeCap>') + x[j:]
open(n + '/conf/logback.xml', 'w').write(x)
PY
diff "$T/logback.shipped.xml" "$T/conf/logback.xml" > "$T/logback.diff" || true
echo "node conf $T/conf: cqllog=$cql threshold=$lvl"; cat "$T/logback.diff"
