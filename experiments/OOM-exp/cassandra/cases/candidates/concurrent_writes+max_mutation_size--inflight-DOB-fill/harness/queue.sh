#!/usr/bin/env bash
# Run arms from a queue file: one line per arm "<name> <direct> <blob> <writers> <infl> <rate> [W=secs] [ENV=VAL ...]".
H=$(cd "$(dirname "$0")" && pwd)
while read -r name d b w i r rest; do
  [ -z "$name" ] && continue
  W=90; envs=()
  for kv in $rest; do case $kv in W=*) W=${kv#W=} ;; *) envs+=("$kv") ;; esac; done
  [ -f /mydata/u1/STOP ] && { echo "STOP file, skipping $name"; continue; }
  env "${envs[@]}" "$H/arm.sh" "$name" "$d" "$b" "$w" "$i" "$r" "$W" > /mydata/u1/runs/$name.out 2>&1
done < "$1"
