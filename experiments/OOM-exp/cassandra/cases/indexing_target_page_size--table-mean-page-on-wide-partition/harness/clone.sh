#!/usr/bin/env bash
# B20: clone.sh <src node dir> <dst node dir>. Real copy of every file except the wide sstable's *-Data.db of ks.t
# (any ks/t-*/*-Data.db >= 1 GB), which is hard-linked (sstables are immutable; a lifetime only adds or unlinks files).
set -euo pipefail
S=$1 D=$2
[ -e "$D" ] && { echo "clone: $D exists"; exit 1; }
mkdir -p "$D"
( cd "$S" && find . -type d ) | while read -r d; do mkdir -p "$D/$d"; done
( cd "$S" && find . -type f ) | while read -r f; do
  case $f in
    ./data/ks/t-*/*-Data.db) if [ "$(stat -c %s "$S/$f")" -ge 1000000000 ]; then ln "$S/$f" "$D/$f"; continue; fi;;
  esac
  cp -p "$S/$f" "$D/$f"
done
echo "clone ok: $(du -sh "$D" | cut -f1) (hard-linked: $(find "$D" -type f -links +1 | wc -l))"
