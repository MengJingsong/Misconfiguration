#!/usr/bin/env bash
# R24 DIAG-A (calibration, design §2.5 step 5; not a readings arm): victim heap 8 GiB (calibration only), peer 16 GiB, Q = 1.
# QUORUM, F = 128: 5 sequential first pages each on w2k, w4k, w8k, w12k; then w2k at F = 1,024 x 3; w4k at CL ONE x 3;
# w2k with LIMIT 10 x 3. After each part: K histogram (recent buckets), ShortReadProtectionRequests and RFP-request counts by JMX.
#   diag-a.sh [label=DIAG-A] [heap=8G] [diag]   (diag = Byteman rfp.btm probe, used for DIAG-B)
set -uo pipefail
L=${1:-DIAG-A}; HEAP=${2:-8G}; DG=${3:-}
ROOT=/mydata/s4/r24; H=$ROOT/harness; R=$ROOT/runs/$L; V="bash $H/ctl.sh"; C="bash $H/client.sh"
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/cached_rows_fail_threshold--rfp-whole-partition-sized-protection
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V prep "$L" CLONE || exit 1
$V start "$L" 1 "$HEAP" auto $DG && $V ready "$L" 1 && $V start "$L" 2 16G auto && $V ready "$L" 2 && $V ring "$L" || { $V stop "$L"; exit 1; }
TABLES="w2k w4k w8k w12k s2k" $V rfpk "$L" start > /dev/null
q(){ local tag=$1 tbl=$2 cl=$3 f=$4 n=$5 lim=${6:-0}
     $C "$L" one 127.0.0.1 "$tbl" "$cl" "$f" "$n" "$lim" 2>&1 | grep -v '^SLF4J' | sed "s/^/$tag /" | tee -a "$R/diag-client.txt"
     TABLES="$tbl" $V rfpk "$L" "after-$tag" > /dev/null; tail -1 "$R/rfpk.txt" > /dev/null; grep "after-$tag $tbl" "$R/rfpk.txt"; }
for n in 2 4 8 12; do q ladder-w${n}k w${n}k QUORUM 128 5; done
q f1024-w2k w2k QUORUM 1024 3
q one-w4k w4k ONE 128 3
q limit10-w2k w2k QUORUM 128 3 10
[ -n "$DG" ] && cp "$R/probe.txt" "$R/probe.keep" 2>/dev/null
$V stop "$L"
D=$REPO/logs/$L; mkdir -p "$D"
cp "$R"/{diag-client.txt,rfpk.txt,run.meta,ring.txt,probe.txt} "$D"/ 2>/dev/null
grep -h 'Replica filtering protection\|Oversized\|overloaded; dropping\|cached over' "$R/n1/logs/system.log" | cut -c1-300 | head > "$D/rfp-excerpt.txt"
python3 "$H/bk.py" "$D/rfpk.txt" > "$D/rfpk-decoded.txt"
log "$L done"
