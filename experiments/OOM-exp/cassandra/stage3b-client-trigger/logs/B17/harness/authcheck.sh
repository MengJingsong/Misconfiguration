#!/usr/bin/env bash
# B17 3-b confirm lifetime AUTHCHECK (pc75, 2026-11-23; heap 8G / direct 4096M, auth on, fresh template copy, discarded;
# not a reading): the claims of the 3-b analysis that rested on code reading, as each role (B17Auth).
set -uo pipefail
ROOT=/mydata/s4/3b-B17; H=$ROOT/harness; V="bash $H/victim-ctl.sh"
L=${1:-AUTHCHECK}; R=$ROOT/runs/$L; D=$ROOT/out/$L
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V start $L AUTH 8G 4096M && $V ready $L || { echo "INVALID start"; exit 1; }
sleep 5
log "authcheck (roles)"; bash $H/client.sh $L none B17Auth 127.0.0.1 2>&1 | grep -v "^\s*at \|SchemaParser\|IllegalArg\|^\s*\.\.\." > $R/authcheck.txt; cat $R/authcheck.txt
grep -h -i -m8 'guardrail\|mutation.*too large\|exceeds\|Cannot page' $R/logs/system.log $R/logs/debug.log 2>/dev/null | cut -c1-300 > $R/server-excerpt.txt
$V stop $L
rm -rf $D; mkdir -p $D; cp $R/{run.meta,yaml.diff,authcheck.txt,server-excerpt.txt} $D/ 2>/dev/null
rm -rf $ROOT/node
log "END $L done"
