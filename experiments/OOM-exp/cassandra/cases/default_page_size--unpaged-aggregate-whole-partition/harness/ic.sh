#!/usr/bin/env bash
# U10 IC + CAL-R (one lifetime, 8192M/4096M, arm A; not readings): VERIFY, paging mode, sub-reads per query, read time per n.
set -uo pipefail
ROOT=/mydata/s4/u10-w4; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; L=IC; R=$ROOT/runs/$L
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/default_page_size--unpaged-aggregate-whole-partition
C="bash $H/load.sh IC"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V start $L A 8192M 4096M && $V ready $L || exit 1
log "1 VERIFY"; $C verify 127.0.0.1 8 | grep '^verify'
log "2 paging mode"; $C one 127.0.0.1 0 6000 off sel | grep '^one'; $C one 127.0.0.1 0 6000 5000 sel | grep '^one'
log "3 sub-reads per query (Local read count delta)"
for f in off 5000; do
  a=$($V ts $L | awk '/Local read count/{print $NF}'); $C one 127.0.0.1 1 20000 $f agg | grep '^one'
  b=$($V ts $L | awk '/Local read count/{print $NF}'); echo "subreads fetch=$f n=20000 before=$a after=$b delta=$((b-a))"
done
log "4 CAL-R read time per n"
$C cal 127.0.0.1 off 3 8192,16384,32768,49152,65536 | grep '^cal'
$C cal 127.0.0.1 5000 3 8192,16384,32768,49152,65536 | grep '^cal'
$V gc $L; sleep 3; $V read $L end | cut -c1-220
$V oom $L | tail -3
$V stop $L
D=$REPO/logs/IC; mkdir -p $D; cp $R/{run.meta,yaml.diff,readings.csv} $D/ 2>/dev/null; gzip -c $R/samples.csv > $D/samples.csv.gz
python3 $H/gcwin.py $R > $D/gcwin.txt
log "IC done"
