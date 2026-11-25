#!/usr/bin/env bash
# B26: start one lifetime (run-arm.sh) detached on pc91; output in runs/<label>.out.   launch.sh <run-arm args...>
ROOT=/mydata/s4/b26
( setsid nohup bash $ROOT/harness/run-arm.sh "$@" < /dev/null > $ROOT/runs/$1.out 2>&1 & )
echo "launched $1"
