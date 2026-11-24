#!/usr/bin/env bash
# B17 3-b: start one script detached on pc75; output in runs/<label>.out.   launch.sh <script> <label> [args...]
ROOT=/mydata/s4/3b-B17; S=$1; shift
( setsid nohup bash $ROOT/harness/$S "$@" < /dev/null > $ROOT/runs/$1.out 2>&1 & )
echo "launched $S $1"
