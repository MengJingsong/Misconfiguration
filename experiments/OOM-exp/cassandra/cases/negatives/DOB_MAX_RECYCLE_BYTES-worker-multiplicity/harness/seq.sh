#!/usr/bin/env bash
# C3 (2026-11-12): run a list of arms in sequence. Each argument: "name direct_MiB L fill_threads fill_ips burst dump"
cd /mydata/c3
for spec in "$@"; do
  set -- $spec
  tools/c3-run.sh arm "$@" > "logs/$1.out" 2>&1 < /dev/null
  echo "[$(date +%T)] $1 rc=$?"
done
echo SEQ DONE
