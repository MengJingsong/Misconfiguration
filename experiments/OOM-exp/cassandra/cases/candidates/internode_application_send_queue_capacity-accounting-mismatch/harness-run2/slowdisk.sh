#!/usr/bin/env bash
# Set the write delay of the replica's disk (dm-delay over /dev/loop on /mydata/b6/slowdisk.img).
#   slowdisk.sh set <write_ms> | show
# Models a storage stall on the slow replica V (its data, commitlog and hints live on /mydata/b6/slow).
set -euo pipefail
case "${1:-}" in
  set) L=$(sudo dmsetup table b6slow | awk '{print $4}'); S=$(sudo dmsetup table b6slow | awk '{print $2}')
       echo "0 $S delay $L 0 0 $L 0 $2" | sudo dmsetup reload b6slow
       sudo dmsetup suspend --noflush b6slow; sudo dmsetup resume b6slow
       echo "[$(date +%T)] b6slow write delay = $2 ms" ;;
  show) sudo dmsetup table b6slow ;;
  *) echo "usage: $0 set <ms>|show" >&2; exit 2 ;;
esac
