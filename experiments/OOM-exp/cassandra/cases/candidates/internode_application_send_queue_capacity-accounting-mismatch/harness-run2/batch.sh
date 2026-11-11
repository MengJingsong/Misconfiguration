#!/usr/bin/env bash
# B6 run 2 batch: default timeouts, no Byteman, 4 coordinators, Java client, replica disk stall.
H=$(cd "$(dirname "$0")" && pwd)
export HEAPDUMP=0
$H/arm.sh R2_V8g_map_stall_r1  map 1000  8G 8G 30000
$H/arm.sh R2_V8g_blob_stall_r1 blob 11000 8G 8G 30000
$H/arm.sh R2_V6g_map_stall_r1  map 1000  6G 8G 30000
$H/arm.sh R2_V6g_blob_stall_r1 blob 11000 6G 8G 30000
$H/arm.sh R2_V8g_map_nostall   map 1000  8G 8G 0
$H/arm.sh R2_V8g_map_stall_rsv8m map 1000 8G 8G 30000 internode_application_receive_queue_reserve_endpoint_capacity=8MiB
$H/arm.sh R2_V8g_map_stall_r2  map 1000  8G 8G 30000
$H/arm.sh R2_V8g_blob_stall_r2 blob 11000 8G 8G 30000
$H/arm.sh R2_V6g_map_stall_r2  map 1000  6G 8G 30000
$H/arm.sh R2_V6g_map_stall_r3  map 1000  6G 8G 30000
$H/arm.sh R2_V8g_blob_stall_r3 blob 11000 8G 8G 30000
$H/ctl.sh stop all; "$H/slowdisk.sh" set 0
echo BATCH DONE
