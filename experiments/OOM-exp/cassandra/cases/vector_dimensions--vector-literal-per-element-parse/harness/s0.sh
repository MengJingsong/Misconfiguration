#!/usr/bin/env bash
# U17 S0 shakedown (not a reading): one lifetime, D_s (default 500,000), VEC, HEX, WB each N = 1 with 2 sequential
# requests, then readback; arm I: VEC only (class-load source check).   s0.sh <label> <A|I> [D_s]
set -uo pipefail
L=$1 ARM=$2 D=${3:-500000}
ROOT=/mydata/s4/u17; H=$ROOT/harness; R=$ROOT/runs/$L; O=$ROOT/out/$L
V="bash $H/victim-ctl.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V start "$L" "$ARM" 2G auto || exit 1
$V ready "$L" || { $V stop "$L"; exit 1; }
python3 -I "$H/u17client.py" --ddl "$D" | tee "$R/ddl.out"
sleep 30; $V read "$L" base | cut -c1-200
PAYS="VEC HEX WB"; [ "$ARM" = I ] && PAYS="VEC"
for P in $PAYS; do
  mkdir -p "$R/$P"; log "S0 $P"
  timeout 300 python3 -I "$H/u17client.py" --payload $P --d "$D" --n 1 --rounds 2 --out "$R/$P"
  grep -E '^[0-9]|SUMMARY' "$R/$P/client.csv" | awk -F, '/SUMMARY/{print; next}{printf "%s lat_ms=%d %s %s %s\n", $4, $2-$1, $6, $7, $8}'
  $V read "$L" "after-$P" | cut -c1-200
done
python3 -I "$H/u17client.py" --readback | tee "$R/readback.out"
grep -h 'transport.messages.QueryMessage ' "$R/classload.log" | head -3
$V oom "$L" > "$R/oom-check.txt" 2>&1; cat "$R/oom-check.txt"
$V stop "$L"
mkdir -p "$O"; cp "$R"/{run.meta,yaml.diff,ddl.out,readback.out,readings.csv,oom-check.txt} "$O"/ 2>/dev/null
for P in $PAYS; do cp "$R/$P/client.csv" "$O/client-$P.csv"; done
grep -h 'transport.messages.QueryMessage ' "$R/classload.log" | head -3 > "$O/classload-querymessage.txt"
rm -rf "$ROOT/node"; log "END S0 $L"
