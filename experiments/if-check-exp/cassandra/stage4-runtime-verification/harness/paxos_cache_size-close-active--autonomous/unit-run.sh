#!/usr/bin/env bash
# Unit tier (B2, amendments U1-U7 of 2026-10-27) of paxos_cache_size-close-active--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh <label> [grid] [reps]
#   grid: comma list of P:V:N (P = MiB or auto). Default = the frozen grid of U2 (ii)/U3:
#         0,1,4,16,64,auto at V=8192 N=40000; 0,1,4,16 at V=16 N=200000. reps default 2.
#   For each (P,V,N) and rep: rm -rf build/test/cassandra, ant testsome with -Dtest.jvm.args, copy TEST log and XML.
#   Clone C (default $W/cassandra-run49). Logs: $W/logs/paxos_cache_size-close-active/unit-<label>/
# (structure adapted from harness/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous/unit-run.sh)
set -uo pipefail
LABEL=$1
GRID=${2:-0:8192:40000,1:8192:40000,4:8192:40000,16:8192:40000,64:8192:40000,auto:8192:40000,0:16:200000,1:16:200000,4:16:200000,16:16:200000}
REPS=${3:-2}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run49}
CLS=org.apache.cassandra.service.paxos.PaxosCacheBoundTest
L=$W/logs/paxos_cache_size-close-active/unit-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $LABEL clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) test_sha=$(shasum -a 256 "$H/PaxosCacheBoundTest.java" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16) grid=$GRID reps=$REPS"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is running"; exit 1; }
T=$C/test/unit/org/apache/cassandra/service/paxos/PaxosCacheBoundTest.java
cp "$H/PaxosCacheBoundTest.java" "$T"
NB=""
for cell in ${GRID//,/ }; do
  P=${cell%%:*}; rest=${cell#*:}; V=${rest%%:*}; N=${rest#*:}
  for rep in $(seq 1 "$REPS"); do
    tag="P$P-V$V-r$rep"
    rm -rf "$C"/build/test/logs "$C"/build/test/output/TEST-$CLS.xml "$C"/build/test/cassandra
    JA="-Dpaxos.cap=$P -Dpaxos.v=$V -Dpaxos.n=$N"
    log "+ [$tag] rm -rf build/test/cassandra; ant -Dlocal.repository=\$W/m2 testsome $NB -Dtest.name=$CLS -Dtest.jvm.args=\"$JA\""
    s0=$(date +%s)
    ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome $NB -Dtest.name=$CLS -Dtest.jvm.args="$JA" ) > "$L/ant-$tag.log" 2>&1
    rc=$?
    log "[$tag] ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant-$tag.log" || echo 'no Tests run line')"
    cp "$C/build/test/output/TEST-$CLS.xml" "$L/TEST-$tag.xml" 2>/dev/null || log "[$tag] no JUnit XML"
    TL=$(find "$C/build/test/logs" -name "TEST-$CLS.log" 2>/dev/null | head -1)
    if [ -n "$TL" ]; then cp "$TL" "$L/$tag.log"; else log "[$tag] no test log"; fi
    grep -h 'PCB' "$L/$tag.log" 2>/dev/null | sed 's/^.*\(PCB[-A-Z]*,\)/\1/' > "$L/$tag.pcb"
    log "[$tag] $(grep -c '^PCB,' "$L/$tag.pcb") samples; $(grep '^PCB-START' "$L/$tag.pcb" | head -1); $(grep '^PCB-END' "$L/$tag.pcb" | head -1); last: $(grep '^PCB,' "$L/$tag.pcb" | tail -1)"
    NB="-Dno-build-test=true"
  done
done
rm -f "$T"; rm -rf "$C/build/test/logs" "$C/build/test/output/TEST-$CLS.xml" "$C/build/test/cassandra"
rm -rf "$C/build/test/classes/org/apache/cassandra/service/paxos/PaxosCacheBoundTest"*.class
log "copied test removed; clone git status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
log "unit-run $LABEL done"
