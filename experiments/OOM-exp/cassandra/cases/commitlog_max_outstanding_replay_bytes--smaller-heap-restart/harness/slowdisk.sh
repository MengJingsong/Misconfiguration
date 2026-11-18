#!/usr/bin/env bash
# B15: S2's slowdisk.sh (dm-delay) renamed: 12 GiB sparse loop file /mydata/s4/b15-w3/slowdisk.img -> /dev/mapper/b15slow,
# ext4 mounted (-o discard) on /mydata/s4/b15-w3/vol. Read delay always 0; write delay set by `set <ms>`.
#   slowdisk.sh setup | set <write_ms> | teardown | show
# Change from S2: teardown detaches only this device's loop (never `losetup -D`, other cases' loops may exist).
set -euo pipefail
W=/mydata/s4/b15-w3; N=b15slow
case "${1:-}" in
  setup) sudo modprobe dm-delay; mkdir -p $W/vol
         [ -f $W/slowdisk.img ] || truncate -s 12G $W/slowdisk.img
         L=$(sudo losetup -f --show $W/slowdisk.img); S=$(sudo blockdev --getsz "$L")
         echo "0 $S delay $L 0 0 $L 0 0" | sudo dmsetup create $N
         sudo mkfs.ext4 -q /dev/mapper/$N; sudo mount -o discard /dev/mapper/$N $W/vol; sudo chown "$USER" $W/vol; echo "setup $L" ;;
  set) L=$(sudo dmsetup table $N | awk '{print $4}'); S=$(sudo dmsetup table $N | awk '{print $2}')
       echo "0 $S delay $L 0 0 $L 0 $2" | sudo dmsetup reload $N; sudo dmsetup suspend --noflush $N; sudo dmsetup resume $N
       echo "[$(date +%T)] $N write delay = $2 ms; table: $(sudo dmsetup table $N)" ;;
  teardown) sudo umount $W/vol || true; L=$(sudo dmsetup table $N | awk '{print $4}')
            sudo dmsetup remove $N; LD=$(readlink -f /dev/block/$L); sudo losetup -d "$LD"; rm -f $W/slowdisk.img; echo "teardown ($LD)" ;;
  show) sudo dmsetup table $N ;;
esac
