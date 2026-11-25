#!/usr/bin/env bash
# B12 3-b confirm (ms0604, 2026-11-24): one node lifetime with authentication + authorization on.
#   run.sh <name> CHECK            claim checks + RECENT growth per role (histograms), no victim, no attack
#   run.sh <name> T  [nmax=50000]  stage-2 arm T as role `attacker` (SELECT on b12.t only): 32 conns, SERIAL, 61,440-B
#                                  blob keys on b12.t, no milestones; tenant open loop 60 s before .. 30 s after
#   run.sh <name> NG [nmax=50000]  the same load as role `nogrant` (login, no grants) on system.local with 61,440-B text keys
# Fresh node dir (empty data) -> start (2,048 MiB heap, direct auto, shipped OOM handling, dump to /dev/shm) -> superuser
# creates roles, schema, grants (B12Admin) -> ...
set -uo pipefail
NAME=$1; MODE=$2; NMAX=${3:-50000}
ROOT=/mydata/s4/3b-B12; H=$ROOT/h; NODE=$ROOT/node; R=$ROOT/runs/$NAME; SUM=$ROOT/runs/summary.txt; DUMPD=/dev/shm/3b-B12
APW=att-3b-B12; NPW=nog-3b-B12; TPW=ten-3b-B12
export XMX=2048M BUILD=$ROOT/tree B12_HOST=127.0.0.12
J=$BUILD/build/lib/jars
DCP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$J/slf4j-api-2.0.17.jar:$BUILD/lib/failureaccess-1.0.1.jar"
ms(){ date +%s%3N; }
note(){ echo "$(ms) $(TZ=America/New_York date '+%T') $*" | tee -a "$R/steps.txt"; }
mkdir -p "$ROOT/runs"; rm -rf "$R"; mkdir -p "$R"
pre_fail(){ echo "$NAME: PREFLIGHT FAIL $1" | tee -a "$SUM"; exit 1; }
pgrep -f CassandraDaemon >/dev/null && pre_fail "another CassandraDaemon running"
for p in 7000 7312 9042; do ss -ltn | grep -q "127.0.0.12:$p \|\*:$p \|0.0.0.0:$p " && pre_fail "port $p busy"; done
free_kb=$(df -k --output=avail /mydata | tail -1); [ "$free_kb" -ge $((8*1024*1024)) ] || pre_fail "/mydata free ${free_kb}KB < 8GiB"
shm_kb=$(df -k --output=avail /dev/shm | tail -1); [ "$shm_kb" -ge $((3*1024*1024)) ] || pre_fail "/dev/shm free ${shm_kb}KB < 3GiB"
mav=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo); [ "$mav" -ge $((30*1024*1024)) ] || pre_fail "MemAvailable ${mav}KB < 30GiB"
note "preflight ok name=$NAME mode=$MODE nmax=$NMAX free_kb=$free_kb shm_kb=$shm_kb memavail_kb=$mav loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
md5sum "$BUILD/build/apache-cassandra-5.0.9-SNAPSHOT.jar" >> "$R/steps.txt"
"$H/ctl.sh" gen > "$R/ctl.log" 2>&1 || { echo "$NAME: GEN FAIL" | tee -a "$SUM"; exit 1; }
"$H/ctl.sh" start >> "$R/ctl.log" 2>&1
up=0; for _ in $(seq 90); do grep -q "Starting listening for CQL clients" $NODE/logs/system.log 2>/dev/null && { up=1; break; }; sleep 2; done
VPID=$("$H/ctl.sh" pid); CG=$("$H/ctl.sh" cg)
if [ $up != 1 ] || [ -z "$VPID" ]; then echo "$NAME: START FAIL" | tee -a "$SUM"; "$H/ctl.sh" stop >> "$R/ctl.log" 2>&1; exit 1; fi
note "listening vpid=$VPID cg=$CG"
cp $NODE/yaml.diff "$R/V-yaml.diff"; tr '\0' '\n' < /proc/$VPID/cmdline > "$R/V-cmdline.txt"
jcmd $VPID VM.flags 2>/dev/null | tr ' ' '\n' | grep -E "MaxDirectMemorySize|MaxHeapSize|UseG1GC|G1HeapRegionSize|HeapDumpOnOutOfMemoryError|OnOutOfMemoryError" > "$R/V-flags.txt"
grep -E "OnOutOfMemoryError|HeapDumpPath|HeapDumpOnOutOfMemoryError" "$R/V-cmdline.txt" >> "$R/V-flags.txt"
echo "memory.max=$(cat $CG/memory.max) swap.max=$(cat $CG/memory.swap.max)" >> "$R/V-flags.txt"
# --- superuser: roles, admin schema, grants, settings read-back only ---
java -Xmx256m -Duser=cassandra -Dpass=cassandra -cp "$DCP" B12Admin 127.0.0.12 "$APW" "$NPW" "$TPW" > "$R/admin.txt" 2>&1
note "admin setup rc=$? $(grep -c 'ADMIN ok' "$R/admin.txt") statements"
grep -q "ADMIN ok: GRANT MODIFY ON TABLE vic.kv" "$R/admin.txt" || { note "ADMIN SETUP FAILED: abort"; "$H/ctl.sh" stop >> "$R/ctl.log" 2>&1; echo "$NAME: SETUP FAIL" >> "$SUM"; exit 1; }
CLI="python3 -I $H/b12auth.py"
bash "$H/cg.sh" $VPID "$CG" "$R" > /dev/null 2>&1 & CGP=$!
java -cp "$ROOT/cls" B12Sample 7312 1000 "$R" > "$R/sampler.err" 2>&1 & SMP=$!
histo(){ timeout 120 jcmd $VPID GC.class_histogram > "$R/histo-$1.txt" 2>&1
  echo "histo-$1: $(grep -E 'PaxosState\$Snapshot$|PaxosState\$Key$|PaxosState$| \[B$|^Total' "$R/histo-$1.txt" | awk '{print $NF"="$2"/"$3}' | tr '\n' ' ')" | tee -a "$R/recent.txt"; }
if [ "$MODE" = CHECK ]; then
  {
    echo "== pre-auth (no credentials)"; env -u B12_USER $CLI --preauth
    echo "== wrong password"; B12_USER=attacker B12_PASS=wrong $CLI --checkq C2-wrongpw --cql "SELECT v FROM b12.t LIMIT 1"
    echo "== attacker (SELECT on b12.t only)"
    export B12_USER=attacker B12_PASS=$APW
    $CLI --check C3-serial-61440 --cql "SELECT v FROM b12.t WHERE k = ?" --keytype blob --K 61440 --cl SERIAL
    $CLI --check C3-one-61440 --cql "SELECT v FROM b12.t WHERE k = ?" --keytype blob --K 61440 --cl ONE
    $CLI --check C4-serial-65535 --cql "SELECT v FROM b12.t WHERE k = ?" --keytype blob --K 65535 --cl SERIAL
    $CLI --check C4-serial-65536 --cql "SELECT v FROM b12.t WHERE k = ?" --keytype blob --K 65536 --cl SERIAL
    $CLI --checkq C5-insert --cql "INSERT INTO b12.t (k, v) VALUES (0x01, 1)"
    $CLI --checkq C5-lwt-update --cql "UPDATE b12.t SET v = 1 WHERE k = 0x01 IF v = 0"
    $CLI --checkq C5-vic-select --cql "SELECT v FROM vic.kv LIMIT 1"
    $CLI --checkq C5-create-table --cql "CREATE TABLE b12.t2 (k blob PRIMARY KEY)"
    echo "== nogrant (login, no grants)"
    export B12_USER=nogrant B12_PASS=$NPW
    $CLI --checkq C6-select-b12 --cql "SELECT v FROM b12.t LIMIT 1"
    $CLI --check C6-serial-b12 --cql "SELECT v FROM b12.t WHERE k = ?" --keytype blob --K 61440 --cl SERIAL
    $CLI --check C7-local-one-61440 --cql "SELECT key FROM system.local WHERE key = ?" --keytype text --K 61440 --cl ONE
    $CLI --check C7-local-serial-61440 --cql "SELECT key FROM system.local WHERE key = ?" --keytype text --K 61440 --cl SERIAL
    $CLI --check C7-local-serial-65535 --cql "SELECT key FROM system.local WHERE key = ?" --keytype text --K 65535 --cl SERIAL
    $CLI --check C7-local-serial-65536 --cql "SELECT key FROM system.local WHERE key = ?" --keytype text --K 65536 --cl SERIAL
    $CLI --check C7-schema-serial-61440 --cql "SELECT keyspace_name FROM system_schema.keyspaces WHERE keyspace_name = ?" --keytype text --K 61440 --cl SERIAL
    $CLI --check C7-sizeest-serial-61440 --cql "SELECT keyspace_name FROM system.size_estimates WHERE keyspace_name = ?" --keytype text --K 61440 --cl SERIAL
    $CLI --check C7-vtable-serial --cql "SELECT value FROM system_views.settings WHERE name = ?" --keytype text --K 100 --cl SERIAL
    $CLI --checkq C7-paxos-select --cql "SELECT * FROM system.paxos LIMIT 1"
    echo "== tenant"
    export B12_USER=tenant B12_PASS=$TPW
    $CLI --checkq C8-tenant-b12 --cql "SELECT v FROM b12.t LIMIT 1"
  } > "$R/authcheck.txt" 2>&1
  note "authcheck done: $(grep -c '^CHECK\|^PREAUTH' "$R/authcheck.txt") lines"
  sleep 3; histo 0
  B12_USER=attacker B12_PASS=$APW $CLI --stmt T --cl SERIAL --K 61440 --nmax 2000 --m 2000 --out "$R/load-attacker" > "$R/load-attacker.err" 2>&1
  note "attacker 2,000 SERIAL reads b12.t: $(tail -1 $R/load-attacker/client.txt)"
  sleep 3; histo 1
  B12_USER=nogrant B12_PASS=$NPW $CLI --stmt LOCAL --cl SERIAL --K 61440 --nmax 2000 --m 2000 --out "$R/load-nogrant" > "$R/load-nogrant.err" 2>&1
  note "nogrant 2,000 SERIAL reads system.local: $(tail -1 $R/load-nogrant/client.txt)"
  sleep 3; histo 2
  B12_USER=nogrant B12_PASS=$NPW $CLI --stmt SCHEMA --cl SERIAL --K 61440 --nmax 500 --m 500 --out "$R/load-nogrant-schema" > "$R/load-nogrant-schema.err" 2>&1
  note "nogrant 500 SERIAL reads system_schema.keyspaces: $(tail -1 $R/load-nogrant-schema/client.txt)"
  sleep 3; histo 3
  sleep 2
  kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
  mkdir -p "$R/V-logs"; cp -p $NODE/logs/system.log $NODE/logs/debug.log $NODE/logs/stdout.log "$R/V-logs/" 2>/dev/null
  "$H/ctl.sh" stop > "$R/stop.log" 2>&1
  kill $CGP 2>/dev/null; wait $CGP 2>/dev/null
  rm -rf $NODE/data $NODE/commitlog $NODE/hints $NODE/saved_caches $DUMPD
  echo "$NAME CHECK done" >> "$SUM"; note "RUN DONE"; exit 0
fi
# --- tenant (victim) ---
java -Xmx256m -Duser=tenant -Dpass=$TPW -cp "$DCP" B12Victim setup 127.0.0.12 1000 > "$R/victim-setup.txt" 2>&1
note "tenant setup: $(grep 'victim setup' "$R/victim-setup.txt")"
systemd-run --user --scope --quiet --unit="b3b12-tenant-$(date +%s)" -p MemoryMax=2G -p MemorySwapMax=0 \
  java -Xmx512m -Duser=tenant -Dpass=$TPW -cp "$DCP" B12Victim run 127.0.0.12 20 20 "$R/victim.stop" 1500 > "$R/victim.out" 2> "$R/victim.err" &
VICP=$!
note "tenant started"; ms > "$R/victim.start"
sleep 60   # tenant baseline
case $MODE in
  T)  AU=attacker; AP=$APW; ST=T ;;
  NG) AU=nogrant;  AP=$NPW; ST=LOCAL ;;
esac
ms > "$R/attack.start"; note "ATTACK start: role=$AU stmt=$ST SERIAL K=61440 conns=32 nmax=$NMAX (no milestones)"
B12_USER=$AU B12_PASS=$AP $CLI --stmt $ST --cl SERIAL --K 61440 --nmax $NMAX --m $NMAX --out "$R/attack" > "$R/attack.err" 2>&1 &
ATP=$!
dead=""; for _ in $(seq 10000); do kill -0 $VPID 2>/dev/null || { dead=$(ms); break; }; kill -0 $ATP 2>/dev/null || break; sleep 0.1; done
[ -n "$dead" ] && { echo "$dead" > "$R/death.ms"; note "JVM $VPID gone at +$(( dead - $(cat $R/attack.start) )) ms after attack start"; } || note "JVM alive; attack client ended"
wait $ATP; ms > "$R/attack.end"; note "attack client exited: $(grep '^# end' "$R/attack/client.txt")"
sleep 30   # tenant observation after
touch "$R/victim.stop"; wait $VICP 2>/dev/null; note "tenant stopped: $(grep VSUMMARY "$R/victim.out")"
kill $SMP 2>/dev/null; wait $SMP 2>/dev/null
if kill -0 $VPID 2>/dev/null; then st=alive; else st=DEAD; fi
mkdir -p "$R/V-logs"; cp -p $NODE/logs/system.log $NODE/logs/debug.log $NODE/logs/gc.log* $NODE/logs/stdout.log $NODE/logs/launch.log $NODE/logs/hs_err* "$R/V-logs/" 2>/dev/null
"$H/ctl.sh" stop > "$R/stop.log" 2>&1
kill $CGP 2>/dev/null; wait $CGP 2>/dev/null
ls -la $DUMPD/*.hprof 2>/dev/null | tee "$R/hprof.ls" >> "$R/steps.txt"
banner=$(grep -a -m1 "^java.lang.OutOfMemoryError" "$R/V-logs/stdout.log" 2>/dev/null)
if [ -n "$banner" ] && [ $st = DEAD ]; then cls=OOM; elif [ $st = alive ]; then cls=alive; else cls=other; fi
f=$(ls $DUMPD/*.hprof 2>/dev/null | head -1)
if [ -n "$f" ]; then
  note "dump scan start"
  python3 -I "$H/hprof_oome_thread.py" "$f" 40 > "$R/oome-thread.txt" 2>&1
  python3 -I "$H/hprofhist.py" "$f" 40 > "$R/hprofhist.txt" 2>&1
  timeout 1200 python3 -I "$H/bigarrays.py" "$f" 61440 > "$R/bigarrays.txt" 2>&1
  timeout 1200 python3 -I "$H/retainers.py" "$f" byte 61440 8 > "$R/retainers.txt" 2>&1
  rm -f $DUMPD/*.hprof; note "dump scanned and deleted"
fi
line="$NAME mode=$MODE role=$AU auth=on | $cls [$banner] | gone_after_attack_start_ms=$([ -n "$dead" ] && echo $(( dead - $(cat $R/attack.start) )) || echo NA) | client: $(grep '^# end' "$R/attack/client.txt")"
echo "$line" > "$R/outcome.txt"; echo "$line" >> "$SUM"; echo "$line"
python3 -I "$H/vsum.py" "$R" > "$R/vsum.txt" 2>&1
rm -rf $NODE/data $NODE/commitlog $NODE/hints $NODE/saved_caches $DUMPD
note "RUN DONE"
