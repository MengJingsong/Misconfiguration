#!/usr/bin/env bash
# Stage-4 harness, order 9 (PriorityQueue_maxSize-insert-maxSize--autonomous), amendment A3.
# Usage: jdbcount.sh <port> <jdb-log> [wait-seconds]
# Waits until <port> listens (a JVM started with -agentlib:jdwp=...,server=y,suspend=y), attaches jdb,
# sets breakpoints on org.apache.hadoop.util.PriorityQueue.insert and .initialize, resumes every 50 ms
# until the JVM exits, then prints the two hit counts:  JDBCOUNT insert=<n> initialize=<m> attached=<yes|no>
set -u
PORT=${1:?port}; LOG=${2:?log}; WAIT=${3:-1800}
JDB=/usr/lib/jvm/java-8-openjdk-amd64/bin/jdb
for ((i = 0; i < WAIT; i++)); do
  ss -ltn | grep -q ":$PORT " && break
  sleep 1
done
if ! ss -ltn | grep -q ":$PORT "; then echo "JDBCOUNT port $PORT never listened"; exit 2; fi
{ echo "stop in org.apache.hadoop.util.PriorityQueue.insert"
  echo "stop in org.apache.hadoop.util.PriorityQueue.initialize"
  while sleep 0.05; do echo cont || break; done; } | "$JDB" -attach "localhost:$PORT" > "$LOG" 2>&1
ins=$(grep -c "Breakpoint hit:.*PriorityQueue\.insert" "$LOG")
ini=$(grep -c "Breakpoint hit:.*PriorityQueue\.initialize" "$LOG")
att=no; grep -q "Set deferred breakpoint\|Set breakpoint" "$LOG" && att=yes
echo "JDBCOUNT insert=$ins initialize=$ini attached=$att log=$LOG"
