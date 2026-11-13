#!/usr/bin/env bash
# C3 phase B calibration (2026-11-12): burst after a low-T (c=1) and a high-T (4 IPs x 128) fill, direct 2048 MiB (non-binding).
cd /mydata/c3
B=${B:-8000000:400:8:4}; TAG=${TAG:-b8m}
for spec in "cal-$TAG-loT 1 1" "cal-$TAG-hiT 512 4"; do
  set -- $spec
  tools/c3-run.sh arm "$1" 2048 default "$2" "$3" "$B" nodump > "logs/$1.out" 2>&1 < /dev/null
  echo "[$(date +%T)] $1 rc=$?"
done
echo SEQ-CAL $TAG DONE
