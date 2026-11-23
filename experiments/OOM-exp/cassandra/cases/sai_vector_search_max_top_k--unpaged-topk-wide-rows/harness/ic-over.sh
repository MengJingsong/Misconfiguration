#!/usr/bin/env bash
# B21 IC-OVER (optional, not a reading): arm A, heap 8G, fresh template copy; adds table b21.big (1,100 rows x 262,144-char
# body, SAI vector index) in this lifetime's node copy only, flushes, then runs T on b21.big with LIMIT 1000 x2 (5 s apart).
# Predicted: OversizedMessageException ("exceeds allowed maximum of 134217728 bytes") in system.log, client failure/timeout.
#   ic-over.sh IC-OVER
set -uo pipefail
ROOT=/mydata/s4/b21; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
L=${1:-IC-OVER}; R=$ROOT/runs/$L; D=$ROOT/out/$L
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V start $L A 8G && $V ready $L || { echo "INVALID start"; exit 1; }
bash $H/client.sh $L schema-big 127.0.0.1 2>&1 | grep -v "^\s*at \|SchemaParser\|IllegalArg"
bash $H/client.sh $L load-big 127.0.0.1 1100 262144 4 2>&1 | grep -E "load (ok|FAILED)"
$NT flush b21; log "flushed"
( cd $R && bash $H/client.sh $L seq 127.0.0.1 "one:TB:1000:100:2:5000;one:TB:250:100:1:0" > client.out 2> client.err )
grep -E "^Q " $R/client.out | cut -c1-600
$V stop $L
rm -rf $D; mkdir -p $D
cp $R/{run.meta,yaml.diff,client.out} $D/ 2>/dev/null
grep -h -m6 -B1 -A4 'OversizedMessage\|exceeds allowed maximum\|overloaded; dropping' $R/logs/system.log $R/logs/debug.log | cut -c1-400 > $D/internode-excerpt.txt
cat $D/internode-excerpt.txt | head -20
log "END $L"
