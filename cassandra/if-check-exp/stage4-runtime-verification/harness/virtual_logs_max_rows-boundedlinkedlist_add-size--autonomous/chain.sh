#!/usr/bin/env bash
# The whole cluster tier (B3b as amended C4): seven arms one after another. Output: $OUT/<arm>/ and $OUT/chain.log.
H=$(cd "$(dirname "$0")" && pwd); export OUT=${OUT:-$HOME/stage4-logs/vlr/run1/cluster}; mkdir -p "$OUT"
{
for arm in "n1000 1000 on TRACE" "n20000 20000 on TRACE" "n100000 100000 on TRACE" "n200000 200000 on TRACE" "nunset unset on TRACE" "off unset off TRACE" "w1000 1000 on WARN"; do
  set -- $arm
  echo "#### arm $1 $(date -u +%FT%TZ)"
  "$H/cluster-run.sh" "$@" > "$OUT/arm-$1.out" 2>&1; echo "arm $1 rc=$?"
  tail -n 4 "$OUT/arm-$1.out"
done
echo "#### chain done $(date -u +%FT%TZ)"
} 2>&1 | tee "$OUT/chain.log"
