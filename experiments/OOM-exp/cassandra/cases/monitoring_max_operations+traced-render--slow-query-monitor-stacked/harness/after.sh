#!/usr/bin/env bash
# wait until no series.sh runs, then start series.sh with the given specs
while ps -eo cmd | grep -q "[h]arness/series.sh"; do sleep 10; done
exec bash /mydata/s4/r12-w5/harness/series.sh "$@"
