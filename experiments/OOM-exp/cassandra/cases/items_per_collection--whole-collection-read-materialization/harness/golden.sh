#!/usr/bin/env bash
# Golden data load lifetime (design §2.5) or shakedown (instrument check).
# usage: bash golden.sh golden   -> $R/golden/data (s1m b1m r1m s2m s4m s8m), heap 12G guard 28G
#        bash golden.sh shake    -> throwaway node, heap 2G: sz 8 x 1e4 (+bz, rz small), readers sz set 2 30, heap dump, hprof parse
set -uo pipefail
MODEG=$1
source /mydata/s4/u3-w1/harness/lib.sh
D=$R/$MODEG; N=$D/node; L=$D/logs
[ -e "$D" ] && { echo "exists: $D"; exit 2; }
mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,conf} "$L/clients"
preflight
note "GOLDEN mode=$MODEG start_epoch=$(date +%s)"
{ hostname; uname -r; nproc; free -b; df -B1 /mydata | tail -1; java -version 2>&1; python3 --version; swapon --show; } > "$L/env.txt" 2>&1
cp -R "$C/conf/." "$N/conf/"; write_yaml "$N" ""
ulimit -n 100000
client() { log "+ u3client.py $*"; local r; r=$(python3 -I "$H/u3client.py" "$@" 2>>"$L/client.err" | grep '^RESULT'); note "${r:-RESULT missing (see client.err)}"; }
trap 'stop_node; note "END end_epoch=$(date +%s) daemons_left=$(my_daemons | wc -l)"' EXIT
if [ "$MODEG" = golden ]; then
  start_node "$N" 12G 28G u3w1-golden
  client setup
  client loadset s1m 1000000 100000 8
  client loadblob b1m 8000004 8
  client loadrows r1m 1000000 8
  client loadset s2m 2000000 100000 8
  client loadset s4m 4000000 100000 8
  [ "$(date +%H%M)" -lt 0015 ] || [ "$(date +%H)" -ge 20 ] && client loadset s8m 8000000 100000 8
  log "+ flush"; NT flush u3 >> "$L/commands.log" 2>&1
  for t in s1m b1m r1m s2m s4m s8m; do log "+ compact $t"; (cd "$C" && timeout 1200 bin/nodetool compact u3 $t) >> "$L/commands.log" 2>&1; done
  NT tablestats u3 > "$L/tablestats.txt" 2>&1
  note "SIZES $(grep -E 'Table: |SSTable count:|Space used \(live\):' "$L/tablestats.txt" | sed 's/^[[:space:]]*//' | tr '\n' ';')"
  log "+ drain"; (cd "$C" && timeout 300 bin/nodetool drain) >> "$L/commands.log" 2>&1
  stop_node
  mkdir -p "$D/data"; cp -a "$N/data/." "$D/data/"; rm -rf "$D/data/saved_caches"
  note "GOLDEN data du=$(du -sb "$D/data" | cut -f1) commitlog_files=$(ls "$N/commitlog" | wc -l)"
  rm -rf "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
else
  start_node "$N" 2G 16G u3w1-shake
  client setup
  client loadset sz 10000 10000 8
  NT flush u3 >> "$L/commands.log" 2>&1
  start_tpstats
  log "+ readers sz set 2 30"; python3 -I "$H/u3client.py" readers sz set 2 30 "$L/clients/r" > "$L/readers.out" 2>&1
  note "READERS $(cat "$L/readers.out")"
  jcmd "$DPID" GC.heap_dump "$L/shake.hprof" > "$L/heapdump.out" 2>&1
  note "HEAPDUMP $(cat "$L/heapdump.out" | tr '\n' ' ') size=$(stat -c %s "$L/shake.hprof")"
  jcmd "$DPID" GC.class_histogram > "$L/histo-end.txt" 2>&1
  stop_node
  rm -rf "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
fi
