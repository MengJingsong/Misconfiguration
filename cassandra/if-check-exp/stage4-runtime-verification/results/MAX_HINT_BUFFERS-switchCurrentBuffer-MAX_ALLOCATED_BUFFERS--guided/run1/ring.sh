#!/usr/bin/env bash
# Stage 4, run 1, cluster tier — the ring's first-time step (case 9c, "cluster tier, first time only"),
# run once from the workstation before cluster-run.sh. environment.md §5 has the node set-up.
#
#   start node 1 (node0) and node 2 (pc80), no agent; wait for two UN and the native transport;
#   create keyspace1 with RF = 2; write the stress table; stop node 2 and wait until node 1 shows it DN;
#   stop node 1.
#
# Both nodes are left STOPPED with the ring's data in place: node 2 is a ring member, and node 1 holds
# keyspace1. cluster-run.sh then restarts node 1 alone for every capacity value. Refuses to run if either
# node has a data/ directory or a running daemon. Output: $OUT (default ./ring-out)/session.log.
set -uo pipefail
N0=${N0:-jason92@pc66.cloudlab.umass.edu}
N1=${N1:-jason92@pc80.cloudlab.umass.edu}
OUT=${OUT:-$PWD/ring-out}
mkdir -p "$OUT"; exec > >(tee "$OUT/session.log") 2>&1

C='$HOME/cassandra-run1'; C2='$HOME/cassandra-node2'
IP1=198.22.255.77; IP2=198.22.255.91
log() { echo "[$(date '+%F %T')] $*"; }
r0()  { ssh -o BatchMode=yes -n "$N0" "$@"; }
r1()  { ssh -o BatchMode=yes -n "$N1" "$@"; }
die() { log "FAIL: $*"; exit 1; }

log "script: $0"
r0 "pgrep -f '[C]assandraDaemon'" > /dev/null && die "a daemon is running on node 1"
r1 "pgrep -f '[C]assandraDaemon'" > /dev/null && die "a daemon is running on node 2"
r0 "test -e $C/data" && die "node 1 has a data/ directory; remove it (or keep the ring you have)"
r1 "test -e $C2/data" && die "node 2 has a data/ directory; remove it (or keep the ring you have)"
r0 "mkdir -p \$HOME/stage4-logs/hints/cluster && cd $C && git describe --tags && git diff -U0 conf/cassandra.yaml | grep -c '^+[^+]'"
r1 "cd $C2 && git describe --tags && git diff -U0 conf/cassandra.yaml | grep -c '^+[^+]'"

log "== start both nodes"
r0 "cd $C && bin/cassandra -p cassandra.pid > \$HOME/stage4-logs/hints/cluster/ring-node1-stdout.txt 2>&1"
r1 "cd $C2 && bin/cassandra -p cassandra.pid > \$HOME/stage4-logs/second-node/ring-node2-stdout.txt 2>&1"
ok=0
for i in $(seq 1 60); do
  if [ "$(r0 "cd $C && bin/nodetool status 2>&1 | grep -c '^UN'")" = 2 ] && [ "$(r0 "cd $C && bin/nodetool statusbinary 2>&1")" = running ]; then
    log "ring has 2 UN and node 1's native transport is running (~$((i * 5)) s)"; ok=1; break; fi
  sleep 5
done
[ "$ok" = 1 ] || die "the ring did not form"
r0 "cd $C && bin/nodetool status 2>&1 | grep -E '^(UN|DN)'"

log "== keyspace1 (RF = 2) and the stress table"
r0 "cd $C && bin/cqlsh -e \"CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2};\""
r0 "cd $C && tools/bin/cassandra-stress write n=1000 no-warmup -node 127.0.0.1 2>&1 | grep -E 'Op rate|Total errors'"
r0 "cd $C && bin/cqlsh -e 'DESCRIBE TABLE keyspace1.standard1;' | head -3"

log "== stop node 2, wait until node 1 shows it DN, stop node 1"
r1 "cd $C2 && bin/nodetool stopdaemon 2>&1 | tail -1"
ok=0
for i in $(seq 1 30); do r0 "cd $C && bin/nodetool status 2>&1 | grep -q '^DN.*$IP2'" && { log "node 1 sees node 2 as DN (~$((i * 4)) s)"; ok=1; break; }; sleep 4; done
[ "$ok" = 1 ] || die "node 1 never showed node 2 as DN"
r0 "cd $C && bin/nodetool stopdaemon 2>&1 | tail -1"
for i in $(seq 1 30); do r0 "pgrep -f '[C]assandraDaemon'" > /dev/null || break; sleep 2; done
r0 "pgrep -f '[C]assandraDaemon'" > /dev/null && die "node 1 did not stop"
r1 "pgrep -f '[C]assandraDaemon'" > /dev/null && die "node 2 did not stop"
r0 "test -d $C/data/data/keyspace1" || die "node 1 has no keyspace1 data"
log "RESULT: the ring is formed; both nodes are stopped; node 2 is a member; node 1 holds keyspace1"
