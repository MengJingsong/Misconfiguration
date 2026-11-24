#!/usr/bin/env bash
# U10 3-b confirm lifetime LOAD (2048M/1024M = the T budget, auth on; not a reading). Empty node dir; the superuser runs
# setup-su.cql (roles, admin schema u10.t, victim schema, grants); claim probes; then the ATTACKER (u10atk: SELECT+MODIFY on
# u10.t only) writes P x 65,536 x 16,384 B rows (Random(1000+pk), 64 async prepared inserts, CL ONE, 5 retries) and verifies
# them. No nodetool flush/compact (operator steps; stage 2 used them). The harness then drains and stops the node (a clean
# stop, as the case's LOAD) and the node dir becomes the template every attack lifetime is cloned from.
#   load-data.sh [P=2]
set -uo pipefail
P=${1:-2}; export U10_PARTS=$P
ROOT=/mydata/s4/3b-U10; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
C="bash $H/load.sh LOAD"; R=$ROOT/runs/LOAD
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V start LOAD LOAD 2048M 1024M && $V ready LOAD || exit 1
grep -E '^(authenticator|authorizer|role_manager|network_authorizer)' $R/conf/cassandra.yaml | tee $R/auth-yaml.txt
log "superuser setup"; $C su su 127.0.0.1 $H/setup-su.cql > $R/setup-su.out 2>&1
grep -E '^(>|  OK|  FAIL|  row)' $R/setup-su.out | grep -v 'system_views.settings\|row: name=' | head -40
grep -E 'name=(authenticator|authorizer|role_manager|network_authorizer|read_thresholds_enabled|local_read_size|coordinator_read_size|page_size|partition_size|column_value_size|read_request_timeout|native_transport_max_frame_size|native_transport_max_request_data_in_flight|native_transport_rate_limiting_enabled|native_transport_max_concurrent_connections |memtable_heap_space|memtable_allocation_type|concurrent_reads|aggregation_subpage_size|default_page_size|tombstone)' $R/setup-su.out > $R/settings-readback.txt
cat $R/settings-readback.txt
log "claim probes"
{
  $C none try 127.0.0.1 "SELECT release_version FROM system.local"
  $C u10atk:wrong try 127.0.0.1 "SELECT release_version FROM system.local"
  $C atk try 127.0.0.1 "SELECT k FROM victimks.kv LIMIT 1"
  $C atk try 127.0.0.1 "CREATE TABLE u10.t2 (pk int PRIMARY KEY, v blob)"
  $C atk try 127.0.0.1 "CREATE KEYSPACE u10x WITH replication = {'class':'SimpleStrategy','replication_factor':1}"
  $C atk try 127.0.0.1 "ALTER TABLE u10.t WITH comment = 'x'"
  $C vic try 127.0.0.1 "SELECT ck FROM u10.t LIMIT 1"
  $C atk try 127.0.0.1 "SELECT count(*) FROM u10.t WHERE pk = 0"
} > $R/probes.out 2>&1
grep -E '^(# as|>|  RESULT|  row)' $R/probes.out
log "attacker load (u10atk) P=$P"
time $C atk load 127.0.0.1 $P 65536 16384 > $R/load.out 2>&1; grep -E 'load (ok|FAIL)' $R/load.out | tail -5
$C atk verify 127.0.0.1 $P > $R/verify.out 2>&1; grep '^verify' $R/verify.out
$V ts LOAD | tee $R/tablestats.txt
$V read LOAD end | cut -c1-240
grep -c "OutOfMemoryError" $R/logs/system.log
$V stop LOAD
rm -rf $ROOT/template; mv $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template $ROOT/template/commitlog; ls -la $ROOT/template/data/u10/*/ | head -30
log "LOAD done"
