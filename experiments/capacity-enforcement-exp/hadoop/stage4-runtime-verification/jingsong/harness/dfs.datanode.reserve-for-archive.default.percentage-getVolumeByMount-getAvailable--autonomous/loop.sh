#!/usr/bin/env bash
# Order 29 stage 4: 12 GiB ext4 loop filesystem for the same-mount data dirs (D1-1, D1-5). Runs on pc91.
# Usage: loop.sh up|down|status
set -uo pipefail
RUN=/mydata/jingsong-s4/dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable-run1
IMG=$RUN/loop.img; MNT=$RUN/mnt
run() { echo "+ $*  [$(date '+%F %T %Z')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
case "${1:?}" in
up)
  mkdir -p "$MNT"
  [ -e "$IMG" ] || run truncate -s 12G "$IMG"
  run mkfs.ext4 -q -F -m 0 "$IMG"
  run sudo mount -o loop "$IMG" "$MNT" || exit 1
  run sudo chown "$(id -un):$(id -gn)" "$MNT"
  run losetup -j "$IMG"; run df -B1 "$MNT" ;;
down)
  mountpoint -q "$MNT" && run sudo umount "$MNT"
  for d in $(losetup -j "$IMG" | cut -d: -f1); do run sudo losetup -d "$d"; done
  run losetup -j "$IMG"; mount | grep -c "$MNT" ;;
status) losetup -j "$IMG"; mount | grep "$MNT"; df -B1 "$MNT" ;;
esac
