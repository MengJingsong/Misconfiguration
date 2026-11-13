#!/usr/bin/env bash
# C2 controller (runs on pc96; ssh to apt140 victim and apt138 client). One clean Cassandra lifetime per call.
#   run-arm.sh <label> <A|B|I<rps>> <heap> <steps "N:secs,..."> [maxReads] [conns=16]
#   run-arm.sh <label> <arm> <heap> "slow;<conns>;<perconn:secs,...>;<capsecs>;<drainKBps_per_conn>[;rcvbuf]"   (slowread.py client)
#   env DIRECT (default: resolved by cassandra-env.sh) = MaxDirectMemorySize, e.g. 7936M
#   env ROWS (default 56) = rows of 64 KiB per partition (63 -> 4,128,768 B, just below the 4 MiB threshold)
# 1 start victim, ready; 2 schema + load 64 x 56 x 64 KiB (+ oversize pk 1000: 72 rows) and flush;
# 3 rejection control (one read of pk 1000, one of pk 0); 4 GC + baseline reading;
# 5 client load in the background; readings every 10 s until the client ends or the victim dies;
# 6 end readings, OOM/GC-window check, stop, copy small logs into the repo case folder.
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 STEPS=$4 MAXR=${5:-} CONNS=${6:-16}
REPO=$(cd "$(dirname "$0")/.." && pwd)
V="ssh apt140 bash /mydata/c2/harness/victim-ctl.sh"
CL="ssh apt138 bash /mydata/c2/harness/load.sh"
log(){ echo "[$(date -u '+%FT%TZ')] $*"; }
log "ARM $L arm=$ARM heap=$HEAP steps=$STEPS maxReads=${MAXR:-none} conns=$CONNS"
ssh apt138 "mkdir -p /mydata/c2/runs/$L"
$V start "$L" "$ARM" "$HEAP" ${DIRECT:-} || exit 1
$V ready "$L" || { $V stop "$L"; exit 1; }
$CL schema 10.10.1.1
$CL load 10.10.1.1 64 ${ROWS:-56} 65536 0
$CL load 10.10.1.1 1 72 65536 1000
$V flush "$L"
$CL one 10.10.1.1 1000
$CL one 10.10.1.1 0
sleep 5
$V gc "$L"; sleep 3; $V read "$L" base
if [[ $STEPS == "slow;"* ]]; then
  IFS=";" read -r _ SC SP SS SK SR <<< "$STEPS"
  ssh apt138 "cd /mydata/c2/runs/$L; setsid nohup python3 /mydata/c2/harness/slowread.py 10.10.1.1 $SC '$SP' $SS $SK ${SR:-65536} > client.csv 2> client.err < /dev/null & echo \$! > client.pid"
else
  ssh apt138 "cd /mydata/c2/runs/$L; setsid nohup bash /mydata/c2/harness/load.sh run 10.10.1.1 $CONNS $STEPS 64 $MAXR > client.csv 2> client.err < /dev/null & echo \$! > client.pid"
fi
t0=$(date +%s); dead=0
while true; do
  sleep 10
  if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD at +$(( $(date +%s) - t0 ))s"; dead=1; break; fi
  $V read "$L" "t+$(( $(date +%s) - t0 ))" | cut -c1-200
  ssh apt138 "tail -1 /mydata/c2/runs/$L/client.csv"
  ssh apt138 "kill -0 \$(cat /mydata/c2/runs/$L/client.pid) 2>/dev/null" || break
done
# client: let it finish or stop it
ssh apt138 "p=\$(cat /mydata/c2/runs/$L/client.pid); for i in \$(seq 1 40); do kill -0 \$p 2>/dev/null || break; sleep 1; done; kill \$p 2>/dev/null; pkill -f 'C2Load run'; pkill -f slowread.py; grep SUMMARY /mydata/c2/runs/$L/client.csv; tail -3 /mydata/c2/runs/$L/client.err"
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then
  sleep 10; $V read "$L" end-pre | cut -c1-200; $V gc "$L"; sleep 3; $V read "$L" end-post | cut -c1-200
fi
log "OOM/GC check"; $V oom "$L"
$V stop "$L"
# copy small evidence into the repo
D=$REPO/logs/$L; mkdir -p "$D"
scp -q apt140:/mydata/c2/runs/$L/{readings.csv,samples.csv,yaml.diff,run.meta} "$D"/ 2>/dev/null
ssh apt138 "grep -E '^(t,|[0-9]{13},|SUMMARY)' /mydata/c2/runs/$L/client.csv" > "$D/client.csv"
ssh apt140 "grep -h -m5 -A15 'java.lang.OutOfMemoryError\|OutOfDirectMemoryError' /mydata/c2/runs/$L/logs/system.log /mydata/c2/runs/$L/stdout.log 2>/dev/null | head -80" > "$D/oom-excerpt.txt"
ssh apt140 "grep -h 'SelectStatement.java\|CoordinatorWarnings.java' /mydata/c2/runs/$L/logs/system.log | head -5; grep -c 'Read on table' /mydata/c2/runs/$L/logs/system.log" > "$D/threshold-excerpt.txt"
ssh apt140 "python3 /mydata/c2/harness/gcwin.py /mydata/c2/runs/$L" > "$D/gcwin.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
log "END $L"
