#!/usr/bin/env bash
# B21 3-b confirm lifetime AUTHCHECK (pc72, 2026-11-23; heap 8G, auth on, fresh template copy; not a reading): the
# code-reading claims of the 3-b analysis: pre-auth with hand-made frames (preauth.py), then the role checks (AuthCheck).
#   authcheck.sh AUTHCHECK
set -uo pipefail
ROOT=/mydata/s4/3b-B21; H=$ROOT/harness; V="bash $H/victim-ctl.sh"
L=${1:-AUTHCHECK}; R=$ROOT/runs/$L; D=$ROOT/out/$L
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V start $L AUTH 8G && $V ready $L || { echo "INVALID start"; exit 1; }
sleep 5
log "preauth (raw frames)"; python3 $H/preauth.py 127.0.0.1 > $R/preauth.txt 2>&1; cat $R/preauth.txt
log "authcheck (roles)"; bash $H/client.sh $L none B21Load authcheck 127.0.0.1 2>&1 | grep -v "^\s*at \|SchemaParser\|IllegalArg\|^\s*\.\.\." > $R/authcheck.txt; cat $R/authcheck.txt
grep -h -i -m8 'guardrail\|term size\|exceeds' $R/logs/system.log | cut -c1-300 > $R/guardrail-excerpt.txt
$V stop $L
rm -rf $D; mkdir -p $D; cp $R/{run.meta,yaml.diff,preauth.txt,authcheck.txt,guardrail-excerpt.txt} $D/ 2>/dev/null
log "END $L done"
