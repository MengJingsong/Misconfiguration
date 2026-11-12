#!/usr/bin/env bash
# Run 1 cluster tier: the four labels one after another (S4-A7). usage: bash cluster-all.sh run1
H=$(cd "$(dirname "$0")" && pwd); RUN=${1:-run1}; O=/mydata/jingsong-cass-s4/o53/$RUN/cluster; mkdir -p $O
for spec in "s16k 16KiB true" "s32k 32KiB true" "s4m 4MiB true" "s4m-nostats 4MiB false"; do
  set -- $spec
  bash "$H/cluster-run.sh" "$RUN" "$1" "$2" "$3" 150 25 > "$O/$1.out" 2>&1
  echo "$(date -u +%FT%TZ) $1 exit $?" >> "$O/all.txt"
done
echo "$(date -u +%FT%TZ) all done" >> "$O/all.txt"
