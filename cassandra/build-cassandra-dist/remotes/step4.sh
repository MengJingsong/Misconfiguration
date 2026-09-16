#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT_GUESS="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=/dev/null
source "$REPO_ROOT_GUESS/config/environment.sh"

CASSANDRA_HOME="$MYDATA_CASSANDRA_HOME"
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
