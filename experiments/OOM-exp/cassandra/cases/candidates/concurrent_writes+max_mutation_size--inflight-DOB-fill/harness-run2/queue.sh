#!/usr/bin/env bash
# Run arms from a queue file (pc96): one line per arm "<name> <direct> <blob> <ncoord> <infl> [LOAD=s] [ENV=VAL ...]".
# A STOP file (/mydata/u1r2/STOP) skips the remaining arms.
H=$(cd "$(dirname "$0")" && pwd)
while read -r name d b n i rest; do
  [ -z "$name" ] || [ "${name:0:1}" = "#" ] && continue
  L=90; envs=()
  for kv in $rest; do case $kv in LOAD=*) L=${kv#LOAD=} ;; *) envs+=("$kv") ;; esac; done
  [ -f /mydata/u1r2/STOP ] && { echo "STOP file, skipping $name"; continue; }
  env "${envs[@]}" "$H/arm.sh" "$name" "$d" "$b" "$n" "$i" "$L" > /mydata/u1r2/mirror/$name.out 2>&1
done < "$1"
