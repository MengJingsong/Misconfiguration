#!/usr/bin/env bash
# Pull the small evidence of finished lifetimes from pc91 into logs/<label>/ (run from the case folder).
for L in "$@"; do
  mkdir -p "logs/$L"
  scp -q -r "pc91:/mydata/s4/r14/runs/$L/small/*" "logs/$L/" 2>/dev/null
  scp -q "pc91:/mydata/s4/r14/runs/$L.driver.log" "logs/$L/driver.log" 2>/dev/null
done
