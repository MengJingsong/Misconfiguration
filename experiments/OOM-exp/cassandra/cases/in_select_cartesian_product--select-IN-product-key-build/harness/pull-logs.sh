#!/usr/bin/env bash
# Pull the small evidence of finished lifetimes from ms0617 into logs/<label>/ (run from the case folder).
#   pull-logs.sh <label> ...
for L in "$@"; do
  mkdir -p "logs/$L"
  scp -q -r "ms0617:/mydata/s4/u5-w4/runs/$L/small/*" "logs/$L/" 2>/dev/null || scp -q "ms0617:/mydata/s4/u5-w4/runs/$L/{run.meta,yaml.diff,outcome,client.jsonl,memory.events}" "logs/$L/" 2>/dev/null
  scp -q "ms0617:/mydata/s4/u5-w4/runs/$L.driver.log" "logs/$L/driver.log" 2>/dev/null
done
