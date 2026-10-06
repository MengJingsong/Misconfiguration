#!/usr/bin/env bash
# Stage 4, run 1, cluster tier — cdc_total_space-processNewSegment-allowance, case §9b–§9e.
#
# One node (~/cassandra-run1 on the measured node), restarted once per capacity value; no ring.
#
#   cluster-run.sh smoke            the whole flow at A = 48 MiB with a 10 s B: tests this script's own helpers and the
#                                   instruments. An instrument check, not a reading.
#   cluster-run.sh value <label>    one capacity value, end to end. Labels:
#                                     b144 | b272 | b528   blocking, A = 144, 272, 528 MiB, S = 32 MiB
#                                     bdef                 blocking, cdc_total_space unset: the derived default
#                                     s16                  second-knob arm: blocking, A = 280 MiB, S = 16 MiB
#                                     n144 | n528          non-blocking (scenario C), A = 144, 528 MiB
#                                     c272                 consumer control: blocking, A = 272 MiB, a deleting loop throughout
#   cluster-run.sh all              b144, b272, b528, bdef, s16, n144, n528, c272, in that order
#
# Per value (case 9e): preflight, config, reset, start with cdc-verdict.btm, Submit -l and settings read-back, the sampler,
# control run (15 s idle), the schema (both tables, made while idle), scenario A (unthrottled CDC stress until the first rejection),
# a settle wait (until non-CDC writes have been taken promptly for 15 s in a row), scenario B (60 s throttled CDC stress plus the non-CDC control),
# release (a consumer pass, then a probe write), stop, read the traces. Non-blocking: A ends when the
# trace holds k + 8 segment creations, B runs 30 s, there is no release. Every command is logged with its output to
# ~/stage4-logs/cdc/cluster/<label>/session.log; readings go to readings.csv, notes to summary.txt, phase times to phases.csv.
#
# Exit codes: 1 a check failed (an instrument or set-up fault); 2 usage; 3 scenario A never reached its end (invalid run, case
# 9a/9c: fix the workload and repeat); any non-zero exit stops stress, the consumer, the sampler and the node.
# Overridable: A_TIMEOUT (180 s; 600 for bdef), B_SECONDS (60), NB_B_SECONDS (30), C_SECONDS (30), THREADS (16), RATE (100).
set -Euo pipefail

C=$HOME/cassandra-run1
HARNESS=$HOME/stage4-harness-run/cdc             # copy of the committed harness, with SHA256SUMS
L=$HOME/stage4-logs/cdc/cluster
BM=$C/build/lib/jars
THREADS=${THREADS:-16}; RATE=${RATE:-100}
B_SECONDS=${B_SECONDS:-60}; NB_B_SECONDS=${NB_B_SECONDS:-30}; C_SECONDS=${C_SECONDS:-30}
D=""; S=""; PID=""; MODE=""; SAMPLER_PID=""; CONSUMER_PID=""; STRESS_PIDS=""
FAILURES_BEAN='org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Failures'

# ---------------------------------------------------------------- helpers
log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$S"; }
fail() { log "FAIL: $*"; exit 1; }
now()  { date +%s%3N; }
run()  { log "+ $*"; "$@"; local rc=$?; log "  rc=$rc"; return $rc; }
check(){ local d=$1; shift; if "$@"; then log "CHECK PASS: $d"; else fail "CHECK FAILED: $d"; fi; }
expect(){ local d=$1; shift; if "$@"; then note "EXPECTED: $d — yes"; else note "EXPECTED: $d — NO (recorded; the AI judges it in the results file)"; fi; }
daemon_up() { pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' > /dev/null; }
submit() { (cd "$C" && java -cp "$BM/byteman-submit-4.0.20.jar" org.jboss.byteman.agent.submit.Submit "$@" 2>&1); }
phase() { echo "$(now),$1" >> "$D/phases.csv"; log "phase $1"; }

kill_stress() {
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2> /dev/null || true
  local p; for p in $STRESS_PIDS; do kill "$p" 2> /dev/null || true; done; STRESS_PIDS=""
}
cleanup() {
  local rc=$?; trap - EXIT ERR
  [ "$rc" -ne 0 ] && log "EXIT rc=$rc: stopping stress, the consumer, the sampler and the node"
  kill_stress
  [ -n "$CONSUMER_PID" ] && kill "$CONSUMER_PID" 2> /dev/null || true
  [ -n "$SAMPLER_PID" ] && kill -TERM "$SAMPLER_PID" 2> /dev/null || true
  if daemon_up; then (cd "$C" && bin/nodetool stopdaemon) > /dev/null 2>&1 || true
    for _ in $(seq 60); do daemon_up || break; sleep 1; done
    daemon_up && { pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'; sleep 2; }; fi
  daemon_up && log "WARNING: a CassandraDaemon is still running"
  [ -d "$C/conf" ] && (cd "$C" && git checkout -q conf/cassandra.yaml 2> /dev/null) || true
  sleep 1; exit "$rc"
}
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR
trap cleanup EXIT

# The yaml is always rebuilt from the tag plus the arm's edits (case 9e).
#   $1 = cdc_total_space in MiB, or "default" (left unset); $2 = commitlog_segment_size in MiB; $3 = blocking|nonblocking
mk_yaml() {
  cd "$C" || return 1
  git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml
  sed -i 's/^cdc_enabled: false$/cdc_enabled: true/' conf/cassandra.yaml
  [ "$1" != default ] && printf 'cdc_total_space: %sMiB\n' "$1" >> conf/cassandra.yaml
  [ "$3" = nonblocking ] && printf 'cdc_block_writes: false\n' >> conf/cassandra.yaml
  [ "$2" != 32 ] && sed -i "s/^commitlog_segment_size: 32MiB\$/commitlog_segment_size: ${2}MiB/" conf/cassandra.yaml
  return 0
}

start_log() {   # $1 = label
  mkdir -p "$L"; D=$L/$1
  if [ -e "$D" ] && [ -n "$(ls -A "$D" 2> /dev/null)" ]; then mv "$D" "$D.attempt-$(date +%s)"; fi
  mkdir -p "$D"; S=$D/summary.txt; exec > >(tee -a "$D/session.log") 2>&1
  : > "$D/phases.csv"
  log "script: $0 $MODE; host: $(hostname); label: $1"
}

# ---------------------------------------------------------------- readings (case 9d)
mx() {   # bean attribute -> a number; `sjk mx -f` takes one attribute per call and each call starts a JVM
  local raw; raw=$(cd "$C" && bin/nodetool sjk mx -mg -b "$1" -f "$2" 2>&1) || { log "sjk failed: $raw"; return 1; }
  echo "$raw" | awk 'NF{l=$0} END{n=split(l,a,/[ \t:=]+/); print a[n]}'
}
write_failures() { local v; v=$(mx "$FAILURES_BEAN" Count) || v=NA; [[ "$v" =~ ^[0-9]+$ ]] || v=NA; echo "$v"; }
warn_count()  { grep -c '^WARN.*Rejecting mutation to keyspace' "$C/logs/system.log" 2> /dev/null || true; }   # the rate-limited WARN entries
stack_count() { grep -c '^org.apache.cassandra.exceptions.CDCWriteException' "$C/logs/system.log" 2> /dev/null || true; }   # one logged exception per rejected write
pre_count()   { grep -c '^pre ' "$D/cdc-verdict.txt" 2> /dev/null || true; }
forb_count()  { grep -c 'state=FORBIDDEN' "$D/cdc-verdict.txt" 2> /dev/null || true; }
# reading <phase> full|light -> a row in readings.csv from the sampler's last row and the counts
reading() {
  local phase=$1 kind=$2 row fail="" ms links bytes alloc idxf idxb
  row=$(tail -1 "$D/sampler.csv")
  IFS=, read -r ms links bytes alloc idxf idxb _ _ <<< "$row"
  [ "$kind" = full ] && fail=$(write_failures)
  echo "$phase,$ms,$links,$bytes,$alloc,$idxf,$idxb,${fail:-},$(warn_count),$(pre_count),$(forb_count)" >> "$D/readings.csv"
  log "reading $phase: links=$links link_bytes=$bytes alloc=$alloc idx=$idxf/$idxb Failures=${fail:-} WARN=$(warn_count) created=$(pre_count) forbidden=$(forb_count)"
  LAST_LINKS=$links
}
wait_for() { local d=$1 t=$2 i=0; shift 2
  until "$@"; do sleep 1; i=$((i + 1)); [ "$i" -ge "$t" ] && fail "timeout ${t}s waiting for: $d"; done; log "ok: $d (after ${i}s)"; }
node_ready() { [ -s "$C/cassandra.pid" ] && [ "$(cd "$C" && bin/nodetool statusbinary 2>&1)" = running ] \
               && (cd "$C" && bin/nodetool status 2>&1 | grep -q '^UN'); }

# ---------------------------------------------------------------- start the node (case 9e, "Start the node the same way")
start_node() {
  local opts="-Dstage4.byteman.out=$D/cdc-verdict.txt -javaagent:$BM/byteman-4.0.20.jar=script:$HARNESS/cdc-verdict.btm,listener:true"
  note "JVM_EXTRA_OPTS=$opts"
  log "+ JVM_EXTRA_OPTS=... bin/cassandra -p cassandra.pid > $D/stdout.txt 2>&1"
  (cd "$C" && JVM_EXTRA_OPTS="$opts" bin/cassandra -p cassandra.pid > "$D/stdout.txt" 2>&1)
  local i=0
  until node_ready; do
    sleep 1; i=$((i + 1))
    daemon_up || fail "the daemon died during start-up (see $D/stdout.txt)"
    [ "$i" -ge 240 ] && fail "timeout 240s waiting for the node to be UN with the native port running"
  done
  PID=$(cat "$C/cassandra.pid"); note "node pid $PID, up at $(now) (after ${i}s)"
  submit -l > "$D/submit-l.txt"; sed 's/^/    | /' "$D/submit-l.txt" | head -40 >&2
  check "Submit -l lists CDCSizeTracker.processNewSegment" grep -q 'processNewSegment' "$D/submit-l.txt"
  check "Submit -l lists deleteOldLinkedCDCCommitLogSegment" grep -q 'deleteOldLinkedCDCCommitLogSegment' "$D/submit-l.txt"
  check "Submit -l lists CDCWriteException" grep -q 'CDCWriteException' "$D/submit-l.txt"
}

read_settings() {   # -> $D/settings.txt; sets A_RES (resolved cdc_total_space, MiB) and SEG_RES
  (cd "$C" && bin/cqlsh -e "SELECT name, value FROM system_views.settings WHERE name IN ('cdc_enabled','cdc_total_space','cdc_block_writes','commitlog_segment_size','cdc_raw_directory')") > "$D/settings.txt" 2>&1
  sed 's/^/    | /' "$D/settings.txt" >&2
  A_RES=$(awk -F'|' '/cdc_total_space/{gsub(/[^0-9]/,"",$2); print $2}' "$D/settings.txt")
  SEG_RES=$(awk -F'|' '/commitlog_segment_size/{gsub(/[^0-9]/,"",$2); print $2}' "$D/settings.txt")
  [[ "$A_RES" =~ ^[0-9]+$ ]] || fail "could not read cdc_total_space back: $(cat "$D/settings.txt")"
  [[ "$SEG_RES" =~ ^[0-9]+$ ]] || fail "could not read commitlog_segment_size back"
  note "settings read back: cdc_total_space=${A_RES}MiB commitlog_segment_size=${SEG_RES}MiB cdc_enabled=$(awk -F'|' '/cdc_enabled/{gsub(/ /,"",$2); print $2}' "$D/settings.txt") cdc_block_writes=$(awk -F'|' '/cdc_block_writes/{gsub(/ /,"",$2); print $2}' "$D/settings.txt")"
}

stop_node() {
  [ -n "$SAMPLER_PID" ] && { kill -TERM "$SAMPLER_PID" 2> /dev/null; wait "$SAMPLER_PID" 2> /dev/null; SAMPLER_PID=""; }
  (cd "$C" && bin/nodetool stopdaemon) 2>&1 | tail -1
  local i; for i in $(seq 180); do daemon_up || break; sleep 1; done
  if daemon_up; then note "stopdaemon did not finish in 180 s: kill -9 (the data is discarded)"; pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'; sleep 2; fi
  daemon_up && fail "the node did not stop"
  PID=""
}

# stress helpers: all stress JVMs are started in the background, their output goes to $D/stress-<name>.txt
S_CDC='tools/bin/cassandra-stress user profile=@/cdc-rows.yaml "ops(insert=1)"'
start_stress() {   # name profile-file duration-or-n rate-args...
  local name=$1 prof=$2 dur=$3; shift 3
  log "+ tools/bin/cassandra-stress user profile=$HARNESS/$prof \"ops(insert=1)\" $dur no-warmup $* -errors retries=0 ignore -node 127.0.0.1 > $D/stress-$name.txt &"
  (cd "$C" && tools/bin/cassandra-stress user profile="$HARNESS/$prof" "ops(insert=1)" $dur no-warmup "$@" -errors retries=0 ignore -node 127.0.0.1) > "$D/stress-$name.txt" 2>&1 &
  STRESS_PIDS="$STRESS_PIDS $!"; LAST_STRESS=$!
}

# ---------------------------------------------------------------- one capacity value
value() {
  local label=$1 A_MIB SEG_MIB MODE_ARM KIND=normal a_timeout=${A_TIMEOUT:-180}
  case $label in
    b144) A_MIB=144;     SEG_MIB=32; MODE_ARM=blocking ;;
    b272) A_MIB=272;     SEG_MIB=32; MODE_ARM=blocking ;;
    b528) A_MIB=528;     SEG_MIB=32; MODE_ARM=blocking ;;
    bdef) A_MIB=default; SEG_MIB=32; MODE_ARM=blocking; a_timeout=${A_TIMEOUT:-600} ;;
    s16)  A_MIB=280;     SEG_MIB=16; MODE_ARM=blocking ;;
    n144) A_MIB=144;     SEG_MIB=32; MODE_ARM=nonblocking ;;
    n528) A_MIB=528;     SEG_MIB=32; MODE_ARM=nonblocking ;;
    c272) A_MIB=272;     SEG_MIB=32; MODE_ARM=blocking; KIND=consumer ;;
    smoke) A_MIB=48;     SEG_MIB=32; MODE_ARM=blocking; B_SECONDS=10; a_timeout=120 ;;
    *) echo "unknown label $label" >&2; exit 2 ;;
  esac
  MODE="value $label"; start_log "$label"; cd "$C" || exit 1
  note "== $label: cdc_total_space=${A_MIB}$([ "$A_MIB" != default ] && echo MiB) commitlog_segment_size=${SEG_MIB}MiB mode=$MODE_ARM kind=$KIND; stress threads=$THREADS, B throttle ${RATE}/s"
  echo "phase,ms,links,link_bytes,link_alloc_bytes,idx_files,idx_bytes,Failures,WARN_lines,segments_created,segments_forbidden" > "$D/readings.csv"

  # --- preflight
  check "no CassandraDaemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "ports 7199/9042/9091 free" bash -c '! ss -ltn | grep -q -E ":(7199|9042|9091)\b"'
  check "local disk has >= 25 GB free" test "$(df --output=avail -BG "$HOME" | tail -1 | tr -dc 0-9)" -ge 25
  check "the clone is at cassandra-5.0.9" test "$(git describe --tags)" = cassandra-5.0.9
  [ "$C" = "$HOME/cassandra-run1" ] || fail "unexpected clone path $C"
  ( cd "$HARNESS" && sha256sum -c SHA256SUMS ) || fail "harness copy differs from the committed files"
  check "python3 and cqlsh are available" bash -c 'command -v python3 >/dev/null && test -x bin/cqlsh'

  # --- config (9b): the tag's yaml plus the arm's edits
  mk_yaml "$A_MIB" "$SEG_MIB" "$MODE_ARM"
  git diff -U0 conf/cassandra.yaml > "$D/cassandra.yaml.diff"
  note "yaml diff: $(grep '^[+-][^+-]' "$D/cassandra.yaml.diff" | tr '\n' '|')"
  local want=1                                   # the cdc_enabled line
  [ "$A_MIB" != default ] && want=$((want + 1))  # cdc_total_space
  [ "$MODE_ARM" = nonblocking ] && want=$((want + 1))   # cdc_block_writes
  [ "$SEG_MIB" != 32 ] && want=$((want + 1))     # commitlog_segment_size (the replaced line)
  check "yaml diff adds $want lines" test "$(grep -c '^+[^+]' "$D/cassandra.yaml.diff")" -eq "$want"

  # --- reset (9b): data/ and the commit log are removed, logs/ moved aside
  rm -rf data cassandra.pid
  if [ -d logs ] && [ -n "$(ls -A logs)" ]; then run mv logs "$L/logs.before-$label.$(date +%s)"; fi
  mkdir -p logs

  # --- start, read back, sampler, control run
  start_node
  read_settings
  local K=$(( A_RES / SEG_RES )); note "k = floor($A_RES / $SEG_RES) = $K; exact multiple: $([ $((A_RES % SEG_RES)) = 0 ] && echo yes || echo no)"
  [ "$A_MIB" != default ] && check "cdc_total_space read back as $A_MIB" test "$A_RES" -eq "$A_MIB"
  check "commitlog_segment_size read back as $SEG_MIB" test "$SEG_RES" -eq "$SEG_MIB"
  check "data/cdc_raw exists" test -d data/cdc_raw
  python3 "$HARNESS/cdc-sampler.py" "$C/data/cdc_raw" "$D/sampler" 0.05 &
  SAMPLER_PID=$!; sleep 1
  phase idle_start
  local t0; t0=$(now); while [ $(($(now) - t0)) -lt 15000 ]; do sleep 1; done
  phase idle_end; reading idle full
  expect "idle floor is min(k, 2) = $((K < 2 ? K : 2)) links" test "$LAST_LINKS" -eq $((K < 2 ? K : 2))

  if [ "$KIND" = consumer ]; then
    # --- consumer control: a deleting loop throughout, the writer held to RATE rows a second
    "$HARNESS/cdc-consumer.sh" "$C/data/cdc_raw" loop 0.2 > "$D/consumer.txt" 2>&1 &
    CONSUMER_PID=$!
    phase C_start
    start_stress cdc-C cdc-rows.yaml "duration=${C_SECONDS}s" -rate threads=$THREADS throttle=${RATE}/s
    local cp=$LAST_STRESS el=0 c0; c0=$(now)
    while kill -0 "$cp" 2> /dev/null; do
      reading C light; sleep 5; el=$(( ($(now) - c0) / 1000 ))
      [ "$el" -gt $((C_SECONDS + 60)) ] && { note "C: stress did not end"; kill_stress; break; }
    done
    phase C_end; reading Cend full
    kill "$CONSUMER_PID" 2> /dev/null; wait "$CONSUMER_PID" 2> /dev/null; CONSUMER_PID=""
    grep -E 'Op rate|Total errors|Total partitions' "$D/stress-cdc-C.txt" | tee -a "$S" || true
    note "consumer control: WARN lines = $(warn_count), logged rejected writes = $(stack_count), segments created = $(pre_count), forbidden = $(forb_count), links deleted by the consumer = $(grep -c ',deleted,' "$D/consumer.txt" || true)"
    expect "no rejection in the consumer control" test "$(warn_count)" -eq 0
    finish "$K"; return
  fi

  # --- schema, made while the node is idle: both tables exist before any load (a schema change under load can time out)
  local ddl="CREATE KEYSPACE IF NOT EXISTS stage4cdc WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE IF NOT EXISTS stage4cdc.cdc_rows (id bigint, payload blob, PRIMARY KEY (id)) WITH cdc = true; CREATE TABLE IF NOT EXISTS stage4cdc.plain_rows (id bigint, payload blob, PRIMARY KEY (id)) WITH cdc = false;"
  log "+ bin/cqlsh -e \"$ddl\""
  (cd "$C" && bin/cqlsh -e "$ddl") > "$D/schema.txt" 2>&1 || fail "could not create the schema: $(cat "$D/schema.txt")"
  check "both tables exist" bash -c "cd '$C' && bin/cqlsh -e 'DESCRIBE TABLES' -k stage4cdc 2>&1 | grep -q cdc_rows && bin/cqlsh -e 'DESCRIBE TABLES' -k stage4cdc 2>&1 | grep -q plain_rows"

  # --- scenario A
  phase A_start
  start_stress cdc-A cdc-rows.yaml "n=1000000000" -rate threads=$THREADS
  local ap=$LAST_STRESS waited=0
  if [ "$MODE_ARM" = blocking ]; then
    until [ "$(warn_count)" -ge 1 ]; do
      kill -0 "$ap" 2> /dev/null || { tail -5 "$D/stress-cdc-A.txt" >&2; note "A: stress exited before the first rejection"; exit 3; }
      sleep 0.5; waited=$((waited + 1))
      [ "$waited" -ge $((a_timeout * 2)) ] && { note "A: no rejection within ${a_timeout}s (invalid run, case 9a)"; exit 3; }
    done
    phase A_first_rejection
  else
    until [ "$(pre_count)" -ge $((K + 8)) ]; do
      kill -0 "$ap" 2> /dev/null || { tail -5 "$D/stress-cdc-A.txt" >&2; note "A: stress exited before k + 8 segments were created"; exit 3; }
      sleep 0.5; waited=$((waited + 1))
      [ "$waited" -ge $((a_timeout * 2)) ] && { note "A: fewer than k + 8 segments within ${a_timeout}s (invalid run, case 9a)"; exit 3; }
    done
    phase A_segments_reached
  fi
  kill_stress; phase A_end; reading A full
  note "A: ended at $(now), ~$((waited / 2)) s after the start; stress A tail: $(tail -3 "$D/stress-cdc-A.txt" | tr '\n' '|')"

  # --- settle: B starts only when the node has taken non-CDC writes promptly for a whole commit-log sync period. After a large A (the default
  # arm writes about 4 GiB through the mapped commit log) the first periodic sync after the bulk write can stall every write that must be
  # logged for 10 to 15 s, and a non-CDC write then times out (results §3 defects 4 and 6: the first default-arm attempt lost its control,
  # and the second, whose single prompt probe came just before the sync began, had 4 timeouts). A rejected CDC write never reaches the log.
  # So: probe once a second and require SETTLE_STREAK (15, longer than the 10 s sync period) prompt probes in a row.
  phase settle_start
  local sid=3000000000 sat=0 streak=0 sw0 s_rc=1; sw0=$(now); : > "$D/settle-probe.txt"
  while [ $(($(now) - sw0)) -lt 240000 ] && [ "$streak" -lt "${SETTLE_STREAK:-15}" ]; do
    sat=$((sat + 1)); sid=$((sid + 1))
    local s0 s_out; s0=$(now); s_rc=0
    s_out=$(cd "$C" && timeout 20 bin/cqlsh --request-timeout=5 -e "INSERT INTO stage4cdc.plain_rows (id, payload) VALUES ($sid, 0xdeadbeef)" 2>&1) || s_rc=$?
    if [ "$s_rc" -eq 0 ] && [ $(( $(now) - s0 )) -lt 4000 ]; then streak=$((streak + 1)); else streak=0; fi
    echo "$(now),attempt=$sat,rc=$s_rc,took_ms=$(( $(now) - s0 )),streak=$streak,$(echo "$s_out" | tr '\n' ' ' | cut -c1-120)" >> "$D/settle-probe.txt"
    sleep 1
  done
  phase settle_end
  note "settle: $streak prompt non-CDC writes in a row after $sat probe(s), $(( $(now) - sw0 )) ms (settle-probe.txt)"
  expect "settle: ${SETTLE_STREAK:-15} prompt non-CDC writes in a row within 240 s" test "$streak" -ge "${SETTLE_STREAK:-15}"

  # --- scenario B
  local bsec=$B_SECONDS; [ "$MODE_ARM" = nonblocking ] && bsec=$NB_B_SECONDS
  phase B_start
  start_stress cdc-B cdc-rows.yaml "duration=${bsec}s" -rate threads=$THREADS throttle=${RATE}/s
  local bp=$LAST_STRESS pp=""
  if [ "$MODE_ARM" = blocking ]; then start_stress plain-B plain-rows.yaml "duration=${bsec}s" -rate threads=2 throttle=10/s; pp=$LAST_STRESS; fi
  local b0 el=0; b0=$(now)
  while kill -0 "$bp" 2> /dev/null; do
    reading B light; sleep 5; el=$(( ($(now) - b0) / 1000 ))
    [ "$el" -gt $((bsec + 90)) ] && { note "B: stress did not end within ${bsec}+90 s"; kill_stress; break; }
  done
  [ -n "$pp" ] && while kill -0 "$pp" 2> /dev/null; do sleep 1; el=$(( ($(now) - b0) / 1000 )); [ "$el" -gt $((bsec + 90)) ] && break; done
  phase B_end; reading Bend full
  grep -E 'Op rate|Total errors|Total partitions' "$D/stress-cdc-B.txt" | sed 's/^/CDC stress B: /' | tee -a "$S" || true
  [ -n "$pp" ] && { grep -E 'Op rate|Total errors|Total partitions' "$D/stress-plain-B.txt" | sed 's/^/non-CDC stress B: /' | tee -a "$S" || true; }
  if [ "$MODE_ARM" = blocking ]; then
    expect "non-CDC control: no errors" bash -c "grep -q 'Total errors *: *0 ' '$D/stress-plain-B.txt'"
    expect "non-CDC control: wrote rows" bash -c "[ \$(grep 'Total partitions' '$D/stress-plain-B.txt' | head -1 | sed -E 's/.*: *([0-9,]+).*/\\1/' | tr -d ,) -gt 0 ]"
  else
    expect "non-blocking: the CDC stress had no errors" bash -c "grep -q 'Total errors *: *0 ' '$D/stress-cdc-B.txt'"
    expect "non-blocking: no rejection WARN" test "$(warn_count)" -eq 0
  fi

  # --- release (blocking only): a consumer pass, then probe writes until one is accepted
  if [ "$MODE_ARM" = blocking ]; then
    local linksB=$LAST_LINKS
    phase R_start
    "$HARNESS/cdc-consumer.sh" "$C/data/cdc_raw" once > "$D/consumer-release.txt" 2>&1
    note "release: consumer pass deleted $(grep -c ',deleted,' "$D/consumer-release.txt" || true) links (L was $linksB at B's end)"
    local tr0 attempts=0 accepted=0 id=2000000000; tr0=$(now)
    : > "$D/release-probe.txt"
    while [ $(($(now) - tr0)) -lt 30000 ]; do
      attempts=$((attempts + 1)); id=$((id + 1))
      local out rc=0; out=$(cd "$C" && bin/cqlsh -e "INSERT INTO stage4cdc.cdc_rows (id, payload) VALUES ($id, 0xdeadbeef)" 2>&1) || rc=$?
      echo "$(now),attempt=$attempts,rc=$rc,$(echo "$out" | tr '\n' ' ' | cut -c1-160)" >> "$D/release-probe.txt"
      if [ "$rc" -eq 0 ] && ! echo "$out" | grep -qi -E 'error|failure|exception'; then accepted=1; break; fi
      sleep 0.2
    done
    phase R_end; local r_ms=$(( $(now) - tr0 )); sleep 1; reading Rend full
    note "release: accepted=$accepted after $attempts attempt(s), $r_ms ms from the consumer pass to the accepted write (release-probe.txt has each attempt)"
    expect "release: a CDC write was accepted within 30 s" test "$accepted" -eq 1
  fi
  finish "$K"
}

# stop, copy the logs, read the traces, run the analysis (case 9e, "Stop and read")
finish() {
  local K=$1
  stop_node
  cp "$C/logs/system.log" "$D/system.log"; cp "$C/logs/debug.log" "$D/debug.log" 2> /dev/null || true
  grep -h 'Freed up' "$D/debug.log" 2> /dev/null | head -50 > "$D/debug-freed-up-excerpt.txt" || true
  local created forb warn
  created=$(pre_count); forb=$(forb_count); warn=$(warn_count)
  note "traces: segments created=$created, created forbidden=$forb, 'Rejecting mutation' WARN entries in system.log=$warn, logged rejected writes (exception stacks)=$(stack_count), deleteOld lines=$(grep -c '^deleteOld' "$D/cdc-verdict.txt" || true), reject lines=$(grep -c '^reject ' "$D/cdc-verdict.txt" || true) (last n: $(grep '^reject ' "$D/cdc-verdict.txt" | tail -1 | sed -E 's/.* n=([0-9]+).*/\1/'))"
  note "sampler: $(cat "$D/sampler.summary")"
  note "ERROR entries in system.log: $(grep -c '^ERROR' "$D/system.log" || true) (each rejected write logs one: 'Failed to apply mutation locally'); system.log $(du -h "$D/system.log" | cut -f1); DEBUG 'Freed up' lines in debug.log: $(grep -c 'Freed up' "$D/debug.log" 2> /dev/null || true)"
  note "disk: $(du -sh data 2> /dev/null | cut -f1) data/ ; $(df -h --output=avail "$HOME" | tail -1 | tr -d ' ') free"
  python3 "$HARNESS/cdc-analyze.py" --trace "$D/cdc-verdict.txt" --events "$D/sampler.events" --format sampler \
          --csv "$D/sampler.csv" --phases "$D/phases.csv" --json "$D/analysis.json" > "$D/analysis.txt" 2>&1 || note "analysis script failed: see analysis.txt"
  sed 's/^/    | /' "$D/analysis.txt" | cut -c1-200 >&2
  note "RESULT $MODE: finished at $(now)"
}

# ---------------------------------------------------------------- main
case "${1:-}" in
  smoke) value smoke ;;
  value) [ -n "${2:-}" ] || { echo "usage: $0 value <b144|b272|b528|bdef|s16|n144|n528|c272>" >&2; exit 2; }; value "$2" ;;
  all)   for v in b144 b272 b528 bdef s16 n144 n528 c272; do ( "$0" value "$v" ) || exit $?; done ;;
  *)     echo "usage: $0 smoke | value <label> | all" >&2; exit 2 ;;
esac
