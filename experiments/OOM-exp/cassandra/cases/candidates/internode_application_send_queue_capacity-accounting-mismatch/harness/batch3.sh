#!/usr/bin/env bash
# Default timeouts, higher offered rate (16 client processes).
H=$(cd "$(dirname "$0")" && pwd)
export HEAPDUMP=0
$H/armx.sh D_V2g_map_deftimeout_c16 map 1000 8G 2G 90 16
$H/armx.sh D_S2g_map_deftimeout_c16 map 1000 2G 8G 90 16
$H/ctl.sh stop all
echo BATCH3 DONE
