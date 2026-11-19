#!/usr/bin/env bash
# B16 one clean lifetime on ms0611 (victim + client on the same node, loopback), from U4's run-arm.sh.
#   run-arm.sh <label> <A|I|R|I2> <heap> <tbl t|m> <steps "c:secs,...">
# 1 refuse if a CassandraDaemon runs; disk gate; fresh clone of the template; start; ready (one retry if not ready)
# 2 GC + baseline reading; IC: JFR around one read of m and one read of t, table metrics after each, no client run;
#   otherwise 3 client in the background (warm-up 1 read on m for 15 s, then the steps on <tbl>); readings every 10 s
#   until the client ends or the victim dies; M/I/I2 labels: one GC.class_histogram at load second 100 if alive
# 4 outcome (OOM lines, hprof, last scope memory.events), table metrics + stop a survivor (drain + SIGTERM by PID),
#   copy small files to $ROOT/repo-logs/<label>/ (rsynced to the case folder's logs/ by the controller).
set -uo pipefail
L=$1 ARM=$2 HEAP=$3 TBL=$4 STEPS=$5
ROOT=/mydata/s4/b16-w4; H=$ROOT/harness; R=$ROOT/runs/$L
V="bash $H/victim-ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
log "ARM $L arm=$ARM heap=$HEAP tbl=$TBL steps=$STEPS"
ok=0
for try in 1 2; do
  $V start "$L" "$ARM" "$HEAP" || exit 1
  if $V ready "$L"; then ok=1; break; fi
  log "invalid start (try $try)"; $V stop "$L"; [ -d "$R" ] && mv "$R" "$R.badstart$try"
done
[ $ok = 1 ] || { echo "INVALID not-ready" > "$R/outcome"; exit 1; }
sleep 5; $V gc "$L"; sleep 3; $V read "$L" base | cut -c1-220
dead=0; el=0
if [ "$L" = IC ]; then
  P=$($V pid IC)
  for tb in m t; do
    timeout 60 jcmd "$P" JFR.start name=ic-$tb settings=profile filename=$R/ic-$tb.jfr > /dev/null
    bash "$H/load.sh" IC-one one 127.0.0.1 $tb | tee -a "$R/ic-one.txt"
    timeout 120 jcmd "$P" JFR.stop name=ic-$tb > /dev/null
    $V read IC after-$tb | cut -c1-220; $V tblm IC after-$tb
    python3 "$H/jfrmax.py" "$R/ic-$tb.jfr" | tee -a "$R/ic-jfr.txt" && rm -f "$R/ic-$tb.jfr"
  done
  grep -h "tombstone cells\|local_read_size\|Read on table" "$R/logs/system.log" | cut -c1-300 | tail -6 >> "$R/ic-one.txt"
else
  ( cd "$R" && setsid nohup bash "$H/load.sh" "$L" run 127.0.0.1 8 m 15 "$TBL" "$STEPS" > client.csv 2> client.err < /dev/null & )
  sleep 3; CP=$(pgrep -f "B16Load run 127.0.0.1 8 m 15 $TBL $STEPS" | head -1); echo "$CP" > "$R/client.pid"
  log "client pid $CP"
  t0=$(date +%s); histd=0
  while true; do
    sleep 10
    el=$(( $(date +%s) - t0 ))
    if [ "$($V alive "$L")" != ALIVE ]; then log "VICTIM DEAD at +${el}s"; dead=1; break; fi
    $V read "$L" "t+$el" | cut -c1-260
    tail -1 "$R/client.csv" | cut -c1-240
    if [[ $L =~ ^(M|I|I2)- ]] && [ $histd = 0 ] && [ $el -ge 100 ]; then $V hist "$L" t100; histd=1; fi
    kill -0 "$CP" 2>/dev/null || break
  done
  for i in $(seq 1 40); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
  kill "$CP" 2>/dev/null; sleep 1; kill -9 "$CP" 2>/dev/null
  grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
fi
if [ $dead = 0 ] && [ "$($V alive "$L")" = ALIVE ]; then
  sleep 3; $V read "$L" end-pre | cut -c1-220; [ "$L" != IC ] && $V tblm "$L" end
fi
log "OOM/GC check"; $V oom "$L" > "$R/oom-check.txt" 2>&1; head -40 "$R/oom-check.txt"
$V stop "$L"
oomtype=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -1)
if [ "$L" = IC ]; then
  if [ -n "$oomtype" ]; then echo "IC OOM type=\"$oomtype\"" > "$R/outcome"; else echo "IC done (see ic-one.txt, ic-jfr.txt, tblmetrics.txt)" > "$R/outcome"; fi
elif [ $dead = 1 ] && [ -n "$oomtype" ]; then
  # step at death: the step in effect at the victim's last valid JMX sample (U4's rule, as fixed 2026-11-17)
  ls_t=$(grep -E '^[0-9]{13},[0-9]' "$R/samples.csv" | tail -1 | cut -d, -f1)
  sc=$(awk -F, -v t="$ls_t" '/^[0-9]{13},/ && $1 >= t {print $2; exit}' "$R/client.csv")
  echo "OOM c=$sc type=\"$oomtype\" at+${el}s" > "$R/outcome"
elif [ $dead = 1 ]; then
  echo "DEAD-noOOM at+${el}s (check scope oom_kill: $(cat $R/memory.events.last 2>/dev/null | tr '\n' ' '))" > "$R/outcome"
else
  echo "SURVIVED last_c=$(grep -E '^[0-9]{13},' "$R/client.csv" | tail -1 | cut -d, -f2)" > "$R/outcome"
fi
cat "$R/outcome"
D=$ROOT/repo-logs/$L; mkdir -p "$D"
cp "$R"/{readings.csv,samples.csv,yaml.diff,run.meta,outcome,oom-check.txt,ic-one.txt,ic-jfr.txt,tblmetrics.txt} "$D"/ 2>/dev/null
cp "$R/memory.events.last" "$D/memory.events" 2>/dev/null
[ -f "$R/client.csv" ] && grep -E '^(t,|[0-9]{13},|SUMMARY)' "$R/client.csv" > "$D/client.csv"
tail -20 "$R/client.err" > "$D/client.err.tail" 2>/dev/null; [ -s "$D/client.err.tail" ] || rm -f "$D/client.err.tail"
grep -h -m3 -B2 -A25 'java\.lang\.OutOfMemoryError' "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -120 > "$D/oom-excerpt.txt"
[ -s "$D/oom-excerpt.txt" ] || rm -f "$D/oom-excerpt.txt"
{ echo "count 'tombstone cells' warnings: $(grep -c 'tombstone cells' "$R/logs/system.log")"; echo "count 'Scanned over': $(grep -c 'Scanned over' "$R/logs/system.log")";
  echo "count local_read_size lines: $(grep -v 'Node configuration' "$R/logs/system.log" | grep -c -i 'local_read_size\|LocalReadSize')";
  grep -h 'tombstone cells\|Scanned over' "$R/logs/system.log" | cut -c1-300 | tail -3
  grep -v 'Node configuration' "$R/logs/system.log" | grep -h -m3 -i 'local_read_size\|LocalReadSize\|exceeded' | cut -c1-400; } > "$D/threshold-excerpt.txt"
[ -f "$R/histo-t100.txt" ] && head -40 "$R/histo-t100.txt" > "$D/histo-t100-top.txt"
python3 "$H/gcwin.py" "$R" > "$D/gcwin.txt"
[ -f "$D/client.csv" ] && python3 "$H/steps.py" "$D" > "$D/steps.txt" 2>&1
ls -la "$R" | grep -i 'hprof\|hs_err' > "$D/hprof.ls" || rm -f "$D/hprof.ls"
log "END $L $(cat "$R/outcome")"
