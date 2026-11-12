#!/usr/bin/env bash
# B6 run 4, phase D follow-up (design amendment A1): map r4-r5 at 512 MiB (decision rule after 2/3),
# rate-matched blob x3 and rate-capped map x1 (client capped at 2000 writes/s total).
set -u
H=$(cd "$(dirname "$0")" && pwd); H2=$H/../harness-run2
fails=0
run(){ local n=$1; shift
  echo "=== $(date '+%F %T') $n"
  out=$("$H/arm.sh" "$n" "$@"); echo "$out"
  [ -d /mydata/b6/runs4/$n/S-logs ] && python3 -I "$H/gcwin.py" /mydata/b6/runs4/$n/S-logs | tee -a /mydata/b6/runs4/$n/outcome.txt
  if grep -q "RING FAIL" <<< "$out"; then fails=$((fails+1)); [ $fails -ge 2 ] && { echo ABORT; "$H/ctl.sh" stop all; "$H2/slowdisk.sh" set 0; exit 1; }; else fails=0; fi
}
export HEAPDUMP=1
run R4D_S512m_map_r4 map 1000 512M 30000
run R4D_S512m_map_r5 map 1000 512M 30000
export HEAPDUMP=0 RATE=2000
for r in 1 2 3; do run R4D_S512m_blob_rate2k_r$r blob 11000 512M 30000; done
HEAPDUMP=1 run R4D_S512m_map_rate2k_r1 map 1000 512M 30000
"$H/ctl.sh" stop all; "$H2/slowdisk.sh" set 0
echo "=== $(date '+%F %T') BATCH DONE"; pgrep -a java || echo "no java left"
