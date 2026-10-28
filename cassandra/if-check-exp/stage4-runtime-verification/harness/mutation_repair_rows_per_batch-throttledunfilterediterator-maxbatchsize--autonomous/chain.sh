#!/usr/bin/env bash
# The whole cluster tier (B3b/C3 as amended): six arms one after another, after prep-data.sh. Output: $OUT/<arm>/ and $OUT/chain.log.
H=$(cd "$(dirname "$0")" && pwd); export OUT=${OUT:-$HOME/stage4-logs/mrb/run1/cluster}; mkdir -p "$OUT"
{
for arm in "u100 unset wide_cdc" "n1000 1000 wide_cdc" "n10000 10000 wide_cdc" "n100000 100000 wide_cdc" "n0 0 wide_cdc" "p0 0 wide_plain"; do
  set -- $arm
  echo "#### arm $1 $(date -u +%FT%TZ)"
  "$H/cluster-run.sh" "$@" > "$OUT/arm-$1.out" 2>&1; echo "arm $1 rc=$?"
  grep -v CompileCommand "$OUT/arm-$1.out" | tail -n 8
done
echo "#### chain done $(date -u +%FT%TZ)"
} 2>&1 | tee "$OUT/chain.log"
