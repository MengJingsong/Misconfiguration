#!/usr/bin/env bash
# usage: unit-all.sh <case 1|2|3|4>     Runs the whole unit tier (B2) of one of the four EXCESS_WASTE_* case files, one JVM per (build, modes) cell.
# Output $HOME/stage4-logs/ew/unit-c<case>/<label>.{out,log} (PROBE lines in .out). Builds: mkvariant.sh must have made the variants first.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); c=${1:?case 1|2|3|4}; export OUT=$HOME/stage4-logs/ew/unit-c$c; mkdir -p "$OUT"
r() { "$H/unit-run.sh" "$@" 2>&1 | tail -2; }          # <variant|stock> <modes> <label> [Xmx]
case $c in
  1) r stock direct,burst pristine-direct-burst
     for v in v10m v1m; do r $v direct,burst,stream,cont,control $v-all; done ;;
  2) r stock direct pristine-direct
     for v in v10m v1m v100m; do r $v direct,burst,refill,stream,account,control $v-all; done ;;
  3) r stock direct pristine-direct
     for v in v1m v10m v1g; do r $v direct,burst,stream,cont,control $v-all; done ;;
  4) r stock direct,burst pristine-direct-burst
     for v in v10m v20m; do r $v direct,burst,refill,memo,control $v-all; done ;;
esac
echo "unit tier of case $c done: $(ls "$OUT"/*.out | wc -l) cells"
