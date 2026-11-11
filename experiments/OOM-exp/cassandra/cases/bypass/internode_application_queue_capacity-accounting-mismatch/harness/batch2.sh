#!/usr/bin/env bash
# Interventions (C_*) and default-timeout realism arms (D_*).
H=$(cd "$(dirname "$0")" && pwd)
export HEAPDUMP=0
T="write_request_timeout=60000ms native_transport_timeout=60000ms"
RSV="internode_application_send_queue_reserve_endpoint_capacity=8MiB internode_application_receive_queue_reserve_endpoint_capacity=8MiB"
$H/armx.sh C_S2g_map_rsv8m map 1000 2G 8G 90 1 $T $RSV
$H/armx.sh C_V2g_map_rsv8m map 1000 8G 2G 90 1 $T $RSV
$H/armx.sh D_S2g_map_deftimeout_c4 map 1000 2G 8G 90 4
$H/armx.sh D_V2g_map_deftimeout_c4 map 1000 8G 2G 90 4
$H/ctl.sh stop all
echo BATCH2 DONE
