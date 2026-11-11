#!/usr/bin/env bash
H=$(cd "$(dirname "$0")" && pwd)
export HEAPDUMP=0
for r in 2 3; do
  $H/arm.sh B_S2g_map_r$r map 1000 2G 8G
  $H/arm.sh B_S2g_blob_r$r blob 11000 2G 8G
done
for r in 1 2 3; do
  $H/arm.sh B_V2g_map_r$r map 1000 8G 2G
  $H/arm.sh B_V2g_blob_r$r blob 11000 8G 2G
done
$H/ctl.sh stop all
echo BATCH1 DONE
