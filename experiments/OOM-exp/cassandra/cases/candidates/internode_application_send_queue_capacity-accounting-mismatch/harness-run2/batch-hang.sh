#!/usr/bin/env bash
# B6 run 2, second batch: full disk hang (write delay 600 s, i.e. no write completes during the stall).
H=$(cd "$(dirname "$0")" && pwd)
export HEAPDUMP=0
$H/arm.sh R2H_V8g_map_hang_r1  map 1000  8G 8G 600000
$H/arm.sh R2H_V8g_blob_hang_r1 blob 11000 8G 8G 600000
$H/arm.sh R2H_V8g_map_hang_r2  map 1000  8G 8G 600000
$H/arm.sh R2H_V6g_map_hang_r1  map 1000  6G 8G 600000
$H/ctl.sh stop all; "$H/slowdisk.sh" set 0
echo BATCH DONE
