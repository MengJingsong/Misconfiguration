#!/usr/bin/env bash
# U5 P4 last step: REP-<H>-1..2 at the largest failing heap (auto if CAL-CK-auto OOMed, else 8192M from CAL-CK-8G).
# Waits for "SEQ END A3-P4"; skips if $ROOT/seq.halt exists or if it cannot end by 17:45 EST.
ROOT=/mydata/s4/u5-w4
until grep -q "SEQ END A3-P4" $ROOT/runs/seq-A3-P4.log; do sleep 5; done
if grep -q '^OOM' $ROOT/runs/CAL-CK-auto/outcome 2>/dev/null; then H=auto; K1=400; K2=1600000; W=900; NEED=1200
else H=8192M; K1=160; K2=1600000; W=600; NEED=800; fi
for r in 1 2; do
  now=$(TZ=America/New_York date +%s); lim=$(TZ=America/New_York date -d "today 17:45" +%s)
  [ -f $ROOT/seq.halt ] && { echo "HALT"; break; }
  [ $(( now + NEED )) -gt $lim ] && { echo "skip REP-$H-$r: cannot end by 17:45"; break; }
  bash $ROOT/h/run-arm.sh REP-$H-$r A $H CK $K1 $K2 $W > $ROOT/runs/REP-$H-$r.driver.log 2>&1
  grep '^\[.*END' $ROOT/runs/REP-$H-$r.driver.log | tail -1 | cut -c1-220
done
echo "REP END"
