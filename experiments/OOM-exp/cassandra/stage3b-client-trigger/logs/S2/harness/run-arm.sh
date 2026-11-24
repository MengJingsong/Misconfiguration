#!/usr/bin/env bash
# 3-b confirm S2 (pc91, 2026-11-23): one attack lifetime of condition G1 with authentication + authorization on.
# Clean start (fresh node directories, ring regenerated from the pristine conf, as run 2's arm.sh), then:
#   admin (superuser 'cassandra', only): system_auth RF 3 + repair, roles, admin-made schema, GRANTs (admin1/2.cql)
#   probes (no credentials / attacker / victim)
#   victim preload (as victim), samplers on n1..n3 (S2Poll over local JMX, 3 s), victim run (2 sessions x 40 ops/s,
#   CL QUORUM; V1 via n1, V2 via n2+n3) from 60 s before the attack
#   attack as 'attacker' (MODIFY on b6.t_blob only): run 2's client shape, blob 11 000 B, 8 sessions x 256 in flight,
#   all to n1, CL=ONE, uncapped, LOAD s
#   observation: until n1 is dead (+ VPOST s for the victim's view) or OBS s after the client exited
#   collection: GC readings per node (gcpeak.sh / gcwin.py), OOM lines, dump -> histogram + stacks, dump deleted,
#   victim summary, everything stopped.
#   run-arm.sh <label>       env LOAD (90) OBS (300) VPOST (60) VRATE (40)
set -uo pipefail
L=$1; LOAD=${LOAD:-90} OBS=${OBS:-300} VPOST=${VPOST:-60} VRATE=${VRATE:-40}
ROOT=/mydata/s4/3b-S2; H=$ROOT/harness; R=$ROOT/runs/$L
NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"; C="bash $H/ring-ctl.sh"; CL_="bash $H/client.sh"
CPUC=9,11,13,15,25,27,29,31
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*" | tee -a "$R/arm.log"; }
ms(){ date +%s%3N; }
$C start "$L" || { echo "START FAILED $L"; exit 1; }
log "args: label=$L load=$LOAD obs=$OBS vpost=$VPOST vrate=$VRATE heap=2G x3 RF=3 CL=ONE 8x256 blob 11000"
for k in $(seq 1 60); do grep -qh "Created default superuser role" $R/n*/logs/system.log && break; sleep 2; done
grep -h "Created default superuser role" $R/n*/logs/system.log | head -1 | tee -a "$R/arm.log"
grep -h -E "^(authenticator|authorizer|role_manager|network_authorizer):" $R/n1/conf/cassandra.yaml | tee "$R/auth-settings.txt"
# --- admin (superuser) ---
export S2USER=cassandra S2PASS=cassandra
$CL_ S2Cql 127.0.0.1 $H/admin1.cql > "$R/admin.txt" 2>&1
for p in 7199 7299 7399; do timeout 300 $NT -p $p repair -full system_auth > "$R/repair-$p.txt" 2>&1; echo "repair $p: $(tail -1 $R/repair-$p.txt)" >> "$R/admin.txt"; done
S2CL=QUORUM $CL_ S2Cql 127.0.0.1 $H/admin2.cql >> "$R/admin.txt" 2>&1
log "admin done: $(grep -c ERROR $R/admin.txt) errors"
# --- probes ---
S2USER= S2PASS= $CL_ S2Cql 127.0.0.1 $H/probe-noauth.cql > "$R/probes.txt" 2>&1
S2USER=attacker S2PASS=att-pw $CL_ S2Cql 127.0.0.1 $H/probe-attacker.cql >> "$R/probes.txt" 2>&1
S2USER=victim S2PASS=vic-pw $CL_ S2Cql 127.0.0.1 $H/probe-victim.cql >> "$R/probes.txt" 2>&1
log "probes: $(grep -c 'ERROR\|CONNECT FAILED' $R/probes.txt) refusals"
$NT -p 7199 describering b6 > "$R/describering.txt" 2>&1
# --- victim preload, samplers, victim run ---
S2VUSER=victim S2VPASS=vic-pw $CL_ S2Victim preload 127.0.0.1 10000 > "$R/victim-preload.txt" 2>&1
log "$(tail -1 $R/victim-preload.txt)"
for i in 1 2 3; do
  p=$(cat $R/n$i/cass.pid); port=$((7099 + i * 100))
  ( setsid nohup nice -n 10 taskset -c $CPUC bash -c "while kill -0 $p 2>/dev/null && [ ! -f $R/stop ]; do java -Xmx48m -cp $ROOT/cls S2Poll 3000 $port $p >> $R/n$i/poll.log 2>>$R/n$i/poll.err; sleep 3; done; echo \"\$(date +%s) END\" >> $R/n$i/poll.log" < /dev/null > /dev/null 2>&1 & )
done
( S2VUSER=victim S2VPASS=vic-pw setsid nohup bash $H/client.sh S2Victim run $VRATE 100000 $R/stop < /dev/null > "$R/victim.csv" 2> "$R/victim.err" & )
log "victim + samplers started; attack in 60 s"
sleep 60
# --- attack ---
ms > "$R/attack.start"; log "attack start (as attacker)"
( S2USER=attacker S2PASS=att-pw CL=ONE setsid nohup bash $H/client.sh S2Load run blob 11000 256 $LOAD 0 \
    127.0.0.1,127.0.0.1,127.0.0.1,127.0.0.1,127.0.0.1,127.0.0.1,127.0.0.1,127.0.0.1 < /dev/null > "$R/load.log" 2>&1 & )
sleep 15
( S2USER=cassandra S2PASS=cassandra timeout 90 bash $H/client.sh S2Cql 127.0.0.2 $H/clients-view.cql > "$R/clients-view-n2.txt" 2>&1 & )
( S2USER=cassandra S2PASS=cassandra timeout 90 bash $H/client.sh S2Cql 127.0.0.1 $H/clients-view.cql > "$R/clients-view-n1.txt" 2>&1 & )
T0=$(date +%s); DEAD=""
while :; do
  sleep 5
  [ -z "$DEAD" ] && [ "$($C alive $L 1)" = DEAD ] && { DEAD=$(ms); echo "$DEAD" > "$R/n1.dead"; log "n1 DEAD"; }
  pgrep -f "S2Load run" >/dev/null || break
  [ $(( $(date +%s) - T0 )) -gt $(( LOAD + 200 )) ] && { log "client still running at +$(( LOAD + 200 )) s: killing it"; pkill -f "S2Load run"; sleep 2; break; }
done
ms > "$R/attack.end"; log "attack client exited $(( $(date +%s) - T0 )) s after start: $(grep FINAL $R/load.log)"
# --- observation ---
T1=$(date +%s)
while [ -z "$DEAD" ] && [ $(( $(date +%s) - T1 )) -lt $OBS ]; do
  sleep 5; [ "$($C alive $L 1)" = DEAD ] && { DEAD=$(ms); echo "$DEAD" > "$R/n1.dead"; log "n1 DEAD"; }
done
if [ -n "$DEAD" ]; then log "victim observed $VPOST s after n1's death"; sleep $VPOST; fi
# a dump still being written by a live n1: wait (as run 2's collect.sh)
for k in $(seq 1 60); do [ "$($C alive $L 1)" = ALIVE ] && ls $R/n1/*.hprof >/dev/null 2>&1 && ! grep -q "Heap dump file created" $R/n1/stdout.log 2>/dev/null || break; sleep 5; done
touch "$R/stop"; sleep 3
for i in 1 2 3; do echo "n$i $($C alive $L $i)"; done | tee "$R/alive.txt" | tee -a "$R/arm.log"
for i in 2 3; do timeout 60 $NT -p $((7099 + i * 100)) tpstats > "$R/n$i/tpstats.txt" 2>&1; done
[ "$($C alive $L 1)" = ALIVE ] && timeout 60 $NT -p 7199 tpstats > "$R/n1/tpstats.txt" 2>&1
S2USER=cassandra S2PASS=cassandra timeout 90 $CL_ S2Cql 127.0.0.2 $H/admin3.cql > "$R/admin-after.txt" 2>&1
$C stop "$L" | tee -a "$R/arm.log"
pkill -f "S2Victim run"; pkill -f "S2Load run"; pkill -f "[S]2Poll"; sleep 2
# --- collection ---
python3 - "$R" <<'EOF' > "$R/n1.end.txt"
import glob, re, sys, datetime
d = sys.argv[1]
for f in sorted(glob.glob(d + '/n1/logs/gc.log*')):
    for line in open(f, errors='replace'):
        if 'Entering safepoint region: HeapDumper' in line or 'Entering safepoint region: ReportJavaOutOfMemory' in line:
            ts = re.match(r'\[([^\]]+)\]', line).group(1)
            t = int(datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000)
            print(t, ts, line.split('region: ')[1].strip()); sys.exit(0)
EOF
if [ -s "$R/n1.end.txt" ]; then cp "$R/n1.end.txt" "$R/n1.end"; elif [ -f "$R/n1.dead" ]; then echo "$(cat $R/n1.dead) dead-detected" > "$R/n1.end"; fi
for i in 1 2 3; do
  N=$R/n$i
  echo "n$i: $(grep -c 'java.lang.OutOfMemoryError' $N/logs/system.log 2>/dev/null) OOMError lines in system.log | $(bash $H/gcpeak.sh $N/logs 2048) | $(python3 $H/gcwin.py $N/logs)" >> "$R/outcome.nodes"
  grep -m5 -B1 -A12 'java.lang.OutOfMemoryError' $N/logs/system.log > $N/oom-excerpt.txt 2>/dev/null
  grep -h "OutOfMemory\|HeapDump\|Dumping heap\|Heap dump file" $N/stdout.log > $N/stdout-oom.txt 2>/dev/null
  grep -h "messages were dropped\|timeout expired before reaching the network" $N/logs/system.log 2>/dev/null | cut -c1-300 > $N/drops.txt
done
V=$(cat $R/alive.txt | head -1); O="n1 $( [ -s $R/n1.end.txt ] && echo "OOM ($(cut -d' ' -f3- $R/n1.end.txt))" || echo "no OOM mark")"
echo "$L: $O | $(grep '^n1 ' $R/alive.txt) | attack end-start $(( ($(cat $R/attack.end) - $(cat $R/attack.start)) / 1000 )) s | n1.end-attack.start $( [ -f $R/n1.end ] && echo $(( ($(cut -d' ' -f1 $R/n1.end) - $(cat $R/attack.start)) )) ms ) | client $(grep FINAL $R/load.log)" > "$R/outcome"
cat "$R/outcome" "$R/outcome.nodes" | tee -a "$R/arm.log"
for f in $R/n*/*.hprof; do
  [ -f "$f" ] || continue; n=$(basename $(dirname $f))
  ls -l "$f" > "$R/$n/hprof.ls"
  nice -n 10 taskset -c $CPUC timeout 1800 python3 $H/hprofhist.py "$f" 40 > "$R/$n/dump-hist.txt" 2>&1
  nice -n 10 taskset -c $CPUC timeout 900 python3 $H/hprofstacks.py "$f" OutOfMemoryError > "$R/$n/dump-stacks-oom.txt" 2>&1
  nice -n 10 taskset -c $CPUC timeout 900 python3 $H/hprofstacks.py "$f" performLocally > "$R/$n/dump-stacks-performLocally.txt" 2>&1
  rm -f "$f"; echo "deleted $f" >> "$R/$n/hprof.ls"; log "dump $n scanned and deleted"
done
python3 $H/victimsum.py "$R" > "$R/victim-summary.txt" 2>&1
log "done $L"
