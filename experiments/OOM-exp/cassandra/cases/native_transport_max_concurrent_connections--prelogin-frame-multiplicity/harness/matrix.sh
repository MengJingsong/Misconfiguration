#!/usr/bin/env bash
# U2 stage 2 (2026-11-17): runs a list of runs in order (case §2.5 run matrix). usage: matrix.sh <list-name> "<spec>" ["<spec>" ...]
# spec = "<run-id> <cond> <mode> <k> <hold> <yaml_extra or -> <btm>"; yaml_extra uses "@" for spaces (fixed after AI1: "_" also hit the key).
# Starts no new run after 02:00 America/New_York (2026-11-18), per case §2.7 hard rules.
H=$(cd "$(dirname "$0")" && pwd); C=${C:-/mydata/s4/u2-w1}; NAME=$1; shift
ML=$C/logs/matrix-$NAME.log; mkdir -p "$C/logs"
echo "[$(date '+%F %T')] matrix $NAME start: $*" >> "$ML"
for spec in "$@"; do
  read -r rid cond mode k hold yx btm <<< "$spec"
  hm=$(TZ=America/New_York date +%H%M); d=$(TZ=America/New_York date +%Y%m%d)
  if [ "$d" -gt 20261117 ] && [ "$hm" -ge 0200 ]; then echo "[$(date '+%F %T')] $rid not started: past 02:00 America/New_York" >> "$ML"; continue; fi
  [ -f "$C/STOP" ] && { echo "[$(date '+%F %T')] STOP file present; stopping before $rid" >> "$ML"; break; }
  echo "[$(date '+%F %T')] start $rid ($spec)" >> "$ML"
  bash "$H/run.sh" "$rid" "$cond" "$mode" "$k" "$hold" "${yx//@/ }" "$btm" > "$C/logs/$rid.console" 2>&1
  echo "[$(date '+%F %T')] end $rid rc=$? $(grep '^OUTCOME' "$C/logs/$rid/summary.txt" 2>/dev/null)" >> "$ML"
done
echo "[$(date '+%F %T')] matrix $NAME done" >> "$ML"
