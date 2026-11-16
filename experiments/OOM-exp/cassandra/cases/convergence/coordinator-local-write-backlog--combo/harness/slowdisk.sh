#!/usr/bin/env bash
# dm-delay device for R (apt149): 30 GiB loop file /mydata/s2/slowdisk.img -> /dev/mapper/s2slow, ext4 on /mydata/s2/slow.
#   slowdisk.sh setup | set <write_ms> | teardown | show
set -euo pipefail
case "${1:-}" in
  setup) sudo modprobe dm-delay; mkdir -p /mydata/s2/slow
         [ -f /mydata/s2/slowdisk.img ] || truncate -s 30G /mydata/s2/slowdisk.img
         L=$(sudo losetup -f --show /mydata/s2/slowdisk.img); S=$(sudo blockdev --getsz "$L")
         echo "0 $S delay $L 0 0 $L 0 0" | sudo dmsetup create s2slow
         sudo mkfs.ext4 -q /dev/mapper/s2slow; sudo mount /dev/mapper/s2slow /mydata/s2/slow; sudo chown "$USER" /mydata/s2/slow; echo "setup $L" ;;
  set) L=$(sudo dmsetup table s2slow | awk '{print $4}'); S=$(sudo dmsetup table s2slow | awk '{print $2}')
       echo "0 $S delay $L 0 0 $L 0 $2" | sudo dmsetup reload s2slow; sudo dmsetup suspend --noflush s2slow; sudo dmsetup resume s2slow
       echo "[$(date +%T)] s2slow write delay = $2 ms" ;;
  teardown) sudo umount /mydata/s2/slow || true; L=$(sudo dmsetup table s2slow | awk '{print $4}')
            sudo dmsetup remove s2slow; sudo losetup -d "/dev/block/$L" 2>/dev/null || sudo losetup -D; rm -f /mydata/s2/slowdisk.img; echo teardown ;;
  show) sudo dmsetup table s2slow ;;
esac
