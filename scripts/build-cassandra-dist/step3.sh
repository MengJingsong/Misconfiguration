#!/bin/bash
# Starts the Cassandra daemon on this node (config already written by
# step2.sh). Idempotent: does nothing if Cassandra is already running
# under the pidfile below.
set -euo pipefail

CASSANDRA_HOME="/mydata/apache-cassandra-5.0.7"
PIDFILE="$CASSANDRA_HOME/cassandra.pid"
LOGDIR="$CASSANDRA_HOME/logs"
STDOUT_LOG="$LOGDIR/cassandra-stdout.log"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Cassandra already running (pid $(cat "$PIDFILE"))"
    exit 0
fi
rm -f "$PIDFILE"

mkdir -p "$LOGDIR"

# nohup + redirected/closed stdio so the daemon survives the SSH session
# that launched it closing (bin/cassandra also detaches on its own, but
# this is belt-and-suspenders against SIGHUP during the brief window
# before it does).
nohup "$CASSANDRA_HOME/bin/cassandra" -p "$PIDFILE" \
    > "$STDOUT_LOG" 2>&1 < /dev/null &
disown

echo "Cassandra starting -- stdout: $STDOUT_LOG, system log: $LOGDIR/system.log, pidfile: $PIDFILE"
