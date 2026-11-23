#!/usr/bin/env bash
# B22 DIAG lifetime (calibration, not a readings arm; design §2.5 step 5): victim with Byteman (rfp.btm -> RfpProbe PEAK/RESP lines),
# Q = 1: 10 queries at QUORUM on wide, then 5 at ONE on wide, then 10 at QUORUM on small (sequential first pages).
#   diag.sh [label=DIAG] [parts="wq wo sq"]
set -uo pipefail
L=${1:-DIAG}; PARTS=${2:-"wq wo sq"}
ROOT=/mydata/s4/b22; H=$ROOT/harness; R=$ROOT/runs/$L; V="bash $H/ctl.sh"; C="bash $H/client.sh"
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cached_rows_fail_threshold--rfp-counts-versions-not-bytes
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V prep "$L" CLONE || exit 1
$V start "$L" 1 2G auto diag && $V ready "$L" 1 && $V start "$L" 2 16G auto && $V ready "$L" 2 && $V ring "$L" || { $V stop "$L"; exit 1; }
grep -i byteman "$R/n1/stdout.log" | head -3
$V rfpk "$L" start > /dev/null
q(){ local tbl=$1 cl=$2 n=$3 k; for k in $(seq 1 "$n"); do $C "$L" one 127.0.0.1 "$tbl" "$cl" 2>&1 | grep -v '^SLF4J' | tee -a "$R/diag-client.txt"; done
     $V rfpk "$L" "after-$tbl-$cl" > /dev/null; log "probe lines so far: $(wc -l < "$R/probe.txt" 2>/dev/null)"; }
for p in $PARTS; do case $p in wq) q wide QUORUM 10;; wo) q wide ONE 5;; sq) q small QUORUM 10;; esac; done
$V stop "$L"
D=$REPO/logs/$L; mkdir -p "$D"
cp "$R"/{probe.txt,diag-client.txt,rfpk.txt,run.meta,ring.txt} "$D"/ 2>/dev/null
grep -h 'Replica filtering protection\|Oversized' "$R/n1/logs/system.log" | cut -c1-300 | head > "$D/rfp-excerpt.txt"
log "DIAG done"
