#!/bin/bash
# Stops the Cassandra daemon on this node (pidfile written by step3.sh).
# Idempotent: no-ops if it isn't running.
set -euo pipefail

CASSANDRA_HOME="/mydata/apache-cassandra-5.0.7"
PIDFILE="$CASSANDRA_HOME/cassandra.pid"

if [[ ! -f "$PIDFILE" ]] || ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Cassandra not running"
    rm -f "$PIDFILE"
    exit 0
fi

PID="$(cat "$PIDFILE")"
kill "$PID"

for _ in $(seq 1 60); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 1
done

if kill -0 "$PID" 2>/dev/null; then
    echo "pid $PID still alive after 60s, sending SIGKILL" >&2
    kill -9 "$PID"
    sleep 1
fi

rm -f "$PIDFILE"
echo "Cassandra stopped (was pid $PID)"
