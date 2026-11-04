#!/usr/bin/env bash
# Supplementary diagnostic (not a reading of B2/B3; results section 4.2 part 5): does a write refused at
# OutboundConnection.enqueue stay on the coordinator's heap until the write timeout? Source:
# MessagingService.sendWriteWithCallback (MessagingService.java:421-426) registers the callback, which holds the Message,
# before send() throws OversizedMessageException; the entry leaves RequestCallbacks only when it expires
# (write_request_timeout, 30 s in B3a). Prompted by node A running out of heap in L1M (results section 3, defect 3).
# usage (on pc12, no other node of this harness running): supp-retention.sh <run>
#   two nodes as in B3a at internode_max_message_size 1MiB (directories under /mydata/stage4-ime/supp), 1 client thread x
#   20 INSERTs of 2 MiB at CL ALL through A (each refused), then A's class histogram (GC.class_histogram, live objects)
#   at once, after 40 s (past the 30 s timeout) and the same again for 20 writes at 8MiB (accepted: the callbacks are
#   removed on the responses). Output ~/stage4-logs/ime/<run>/supp-retention/.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; export CASSANDRA_HOME=$C
export IME=/mydata/stage4-ime/supp
O=$HOME/stage4-logs/ime/${1:?run}/supp-retention; mkdir -p "$O"; S=$O/summary.txt; : > "$S"
say() { echo "[$(date +%T)] $*" | tee -a "$S"; }
daemons() { ps -eo comm,args | awk '$1=="java" && /CassandraDaemon/' | wc -l; }
[ "$(daemons)" = 0 ] || { say "a CassandraDaemon is already running: stop"; exit 1; }
start() {  # start <A|B> <limit>
  local n=$1; "$H/make-node-yaml.sh" "$n" "internode_max_message_size=$2" > /dev/null
  ( ulimit -n 100000; cd "$C"; CASSANDRA_CONF=$IME/$n/conf CASSANDRA_LOG_DIR=$IME/$n/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M \
      bin/cassandra -p "$IME/$n/cassandra.pid" > "$IME/$n/stdout.txt" 2>&1 )
}
up() {
  for i in $(seq 1 100); do
    a=$(cd "$C" && bin/nodetool -p 7102 status 2>/dev/null | grep -c '^UN'); b=$(cd "$C" && bin/nodetool -p 7103 statusbinary 2>/dev/null)
    [ "$a" = 2 ] && [ "$b" = running ] && return 0; sleep 3
  done; return 1
}
histo() {  # histo <tag>
  local f=$O/histo-$1.txt; jcmd "$(cat $IME/A/cassandra.pid)" GC.class_histogram > "$f" 2>&1
  say "$1: A live heap: CallbackInfo $(awk '/RequestCallbacks\$CallbackInfo$/ {print $2" instances"}' "$f"), Mutation $(awk '$4=="org.apache.cassandra.db.Mutation" {print $2" instances"}' "$f"), [B $(awk '$4=="[B" {printf "%d instances %.1f MiB", $2, $3/1048576}' "$f"), total $(awk '/^Total/ {printf "%.1f MiB", $3/1048576}' "$f")"
}
stopall() { for p in 7103 7102; do (cd "$C" && bin/nodetool -p $p stopdaemon > /dev/null 2>&1); done
  for i in $(seq 1 60); do [ "$(daemons)" = 0 ] && break; sleep 1; done; }
for lim in 1MiB 8MiB; do
  rm -rf "$IME/A" "$IME/B"
  say "limit $lim: start A, B"; start A $lim; sleep 15; start B $lim
  up || { say "nodes not up"; stopall; exit 1; }
  python3 "$H/client.py" schema 127.0.0.2 >> "$S" 2>&1
  python3 "$H/client.py" setting 127.0.0.2 internode_max_message_size >> "$S" 2>&1
  histo "$lim-before"
  python3 "$H/client.py" load 127.0.0.2 0 1 20 2097152 "$O/keys-$lim.csv" >> "$S" 2>&1
  say "$lim: 20 writes done"
  histo "$lim-t0"
  sleep 40
  histo "$lim-t40"
  say "$lim: A system.log exceeds lines: $(grep -c 'exceeds allowed maximum' $IME/A/logs/system.log)"
  cp "$IME/A/logs/system.log" "$O/A-system-$lim.log"
  stopall; say "$lim: stopped; daemons left $(daemons)"
  rm -rf "$IME/A" "$IME/B"
done
rmdir "$IME" 2>/dev/null || true
say "done; daemons left $(daemons)"
