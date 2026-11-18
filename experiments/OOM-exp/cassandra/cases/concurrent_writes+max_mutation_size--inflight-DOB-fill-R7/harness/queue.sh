#!/usr/bin/env bash
# R7: run arms from a queue file (driver host): one line per arm "<name> <direct> <blob> <infl/writer> [LOAD=s] [ENV=VAL ...]".
# A STOP file (/mydata/s4/r7-w1/STOP) skips the remaining arms. The queue file is re-read after each arm (so lines can be
# appended while it runs); arms already done (mirror/<name>/outcome.txt present) are skipped.
QF=$1; H=$(cd "$(dirname "$0")" && pwd); W=/mydata/s4/r7-w1
while true; do
  next=""
  while read -r name d b i rest; do
    [ -z "$name" ] || [ "${name:0:1}" = "#" ] && continue
    [ -e $W/mirror/$name.started ] && continue
    next="$name $d $b $i $rest"; break
  done < "$QF"
  [ -z "$next" ] && break
  [ -f $W/STOP ] && { echo "STOP file, stopping before $next"; break; }
  set -- $next; name=$1 d=$2 b=$3 i=$4; shift 4
  L=180; envs=()
  for kv in "$@"; do case $kv in LOAD=*) L=${kv#LOAD=} ;; *) envs+=("$kv") ;; esac; done
  touch $W/mirror/$name.started
  env "${envs[@]}" "$H/arm.sh" "$name" "$d" "$b" "$i" "$L" > $W/mirror/$name.out 2>&1
done
echo "queue done $(TZ=America/New_York date +%T)"
