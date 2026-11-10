#!/usr/bin/env bash
# One-shot snapshot of S and V: S outbound counters, V inbound-from-S counters, V MutationStage,
# live class histograms of both (each forces a full GC).
#   snap.sh <outfile-prefix>
set -uo pipefail
P=${1:?prefix}; B=/mydata/b6/cassandra; SP=$(cat /mydata/b6/ring/S/cass.pid); VP=$(cat /mydata/b6/ring/V/cass.pid)
QO="SELECT address, pending_count, pending_bytes, using_reserve_bytes, overload_count, expired_count, sent_count, sent_bytes FROM system_views.internode_outbound;"
QI="SELECT address, using_bytes, using_reserve_bytes, throttled_count, received_count, processed_count, expired_count FROM system_views.internode_inbound;"
$B/bin/cqlsh 127.0.0.13 -e "$QO" > $P.S-out.txt 2>&1
$B/bin/cqlsh 127.0.0.11 -e "$QI" > $P.V-in.txt 2>&1
$B/bin/nodetool -p 7211 tpstats 2>&1 | grep -E "Pool Name|MutationStage" > $P.V-tpstats.txt
date +%s > $P.S-hist.txt; jcmd $SP GC.class_histogram >> $P.S-hist.txt 2>&1
date +%s > $P.V-hist.txt; jcmd $VP GC.class_histogram >> $P.V-hist.txt 2>&1
$B/bin/cqlsh 127.0.0.13 -e "$QO" > $P.S-out-after.txt 2>&1
$B/bin/cqlsh 127.0.0.11 -e "$QI" > $P.V-in-after.txt 2>&1
echo "snap $P: S $(grep -m1 '^Total' $P.S-hist.txt) | V $(grep -m1 '^Total' $P.V-hist.txt) | V MutationStage $(grep MutationStage $P.V-tpstats.txt | awk '{print "active="$2" pending="$3}')"
