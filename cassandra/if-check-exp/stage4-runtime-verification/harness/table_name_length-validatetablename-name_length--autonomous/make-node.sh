#!/usr/bin/env bash
# usage: make-node.sh <node-dir> [yaml_key=value ...]     (B3a)   env: CASSANDRA_HOME (a copy made by copy-source.sh, built)
# Builds <node-dir>/conf from the copy's conf/: the shipped cassandra.yaml with the data, commitlog, hints, saved_caches and cdc_raw
# directories under <node-dir> (local disk) appended, plus the extra key=value arguments (a shipped uncommented key of the same name
# is removed first). One node on 127.0.0.1: native 9042, storage 7000, JMX 7199 (local). Nothing in the copy is changed.
set -euo pipefail
N=${1:?node-dir}; shift
C=${CASSANDRA_HOME:?}
mkdir -p "$N/logs" "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
rm -rf "$N/conf"; cp -r "$C/conf" "$N/conf"
python3 - "$N" "$@" <<'PY'
import re, sys
n, extra = sys.argv[1], sys.argv[2:]
kv = [('data_file_directories', None), ('commitlog_directory', n + '/commitlog'), ('hints_directory', n + '/hints'),
      ('saved_caches_directory', n + '/saved_caches'), ('cdc_raw_directory', n + '/cdc_raw')]
kv += [tuple(e.split('=', 1)) for e in extra]
keys = {k for k, _ in kv}
out = [l for l in open(n + '/conf/cassandra.yaml').read().splitlines() if not re.match(r'^(%s):' % '|'.join(keys), l)]
out.append('# ---- stage4 lines ----')
for k, v in kv:
    if k == 'data_file_directories':
        out += ['data_file_directories:', '    - ' + n + '/data']
    else:
        out.append('%s: %s' % (k, v))
open(n + '/conf/cassandra.yaml', 'w').write('\n'.join(out) + '\n')
PY
echo "node dir $N: $(sed -n '/^# ---- stage4 lines/,$p' "$N/conf/cassandra.yaml" | tr '\n' ';')"
