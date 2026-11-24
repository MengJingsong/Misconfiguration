#!/usr/bin/env bash
# B21: start one script detached on ms0604; output in runs/<label>.out.   launch.sh <script> <label> [args...]
ROOT=/mydata/s4/3b-B21; S=$1; shift
( setsid nohup bash $ROOT/harness/$S "$@" < /dev/null > $ROOT/runs/$1.out 2>&1 & )
echo "launched $S $1"
