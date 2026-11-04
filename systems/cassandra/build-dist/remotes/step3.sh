#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT_GUESS="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=/dev/null
source "$REPO_ROOT_GUESS/config/environment.sh"

CASSANDRA_HOME="$MYDATA_CASSANDRA_HOME"
PIDFILE="$CASSANDRA_HOME/cassandra.pid"
LOGDIR="$CASSANDRA_HOME/logs"
STDOUT_LOG="$LOGDIR/cassandra-stdout.log"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Cassandra already running (pid $(cat "$PIDFILE"))"
    exit 0
fi
rm -f "$PIDFILE"

mkdir -p "$LOGDIR"

nohup "$CASSANDRA_HOME/bin/cassandra" -p "$PIDFILE" \
    > "$STDOUT_LOG" 2>&1 < /dev/null &
disown

echo "Cassandra starting -- stdout: $STDOUT_LOG, system log: $LOGDIR/system.log, pidfile: $PIDFILE"
