#!/usr/bin/env bash
# usage: jmx.sh <bean> <attribute>   — one attribute per call; each call starts a JVM (1 to 2 s)
cd "${CASSANDRA_HOME:-$HOME/cassandra-run1}" && bin/nodetool sjk mx -mg -b "$1" -f "$2" 2>&1 | tail -1
