#!/usr/bin/env bash
# U5 P3 (condition PK) driver: CAL-PK-2G ascending (k1 = 16), stop after the first OOM; N_T-PK = the smallest OOM
# point (8M = 16 x 500,000 if none; the design's prediction); T-PK x3 (+ up to 2 if < 3 OOMs); M-PK x3; I-PK x3.
# Honors $ROOT/seq.halt between lifetimes. Launch detached; poll runs/seq-P3.log for "P3 END".
ROOT=/mydata/s4/u5-w4; RA="bash $ROOT/h/run-arm.sh"
one(){ [ -f "$ROOT/seq.halt" ] && { echo "HALT before $1"; return 1; }; $RA "$@" > "$ROOT/runs/$1.driver.log" 2>&1; grep '^\[.*END' "$ROOT/runs/$1.driver.log" | tail -1 | cut -c1-220; }
isoom(){ grep -q '^OOM' "$ROOT/runs/$1/outcome" 2>/dev/null; }
K2T=""
for k2 in 62500 125000 250000 500000 1000000; do
  N=$(( 16 * k2 / 1000000 ))M; L=CAL-PK-2G-$N
  one $L A 2G PK 16 $k2 240 || break
  if isoom $L; then K2T=$k2; echo "first OOM at $L"; break; fi
done
[ -z "$K2T" ] && { K2T=500000; echo "no CAL-PK OOM: N_T-PK = 16 x 500000 (design prediction)"; }
echo "N_T-PK = 16 x $K2T"
n=0
for r in 1 2 3; do one T-PK-2G-$r A 2G PK 16 $K2T 240 || break; isoom T-PK-2G-$r && n=$((n+1)); done
if [ $n -lt 3 ] && [ $n -ge 1 ]; then for r in 4 5; do one T-PK-2G-$r A 2G PK 16 $K2T 240 || break; isoom T-PK-2G-$r && n=$((n+1)); done; fi
echo "T-PK OOM count $n"
for r in 1 2 3; do one M-PK-2G-$r A 2G PK 1 $(( K2T + 15 )) 240 || break; done
for r in 1 2 3; do one I-PK-2G-$r I 2G PK 16 $K2T 240 || break; done
echo "P3 END"
