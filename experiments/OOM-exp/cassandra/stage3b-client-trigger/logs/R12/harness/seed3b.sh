#!/usr/bin/env bash
# R12 3-b confirm SEED (from seed.sh): auth-enabled tree, empty start at 2 GiB; superuser makes roles, schema, grants;
# the attacker role probes its rights and loads k=1/2/3 with MODIFY; the victim role seeds vks.t; flush, compact, drain, tar.
set -u
W=/mydata/s4/3b-R12; H=$W/harness; T=$W/cassandra-base; R=$W/runs/SEED
mkdir -p $R; exec > $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T) $*"; }
. $W/creds.env
if ps -eo cmd | grep -q '[C]assandraDaemon'; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
rm -rf $T/data $T/logs
( ulimit -n 100000; cd $T; MAX_HEAP_SIZE=2G CASSANDRA_HEAPDUMP_DIR=$R exec systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=3b-r12-SEED -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
PID=
for i in $(seq 1 150); do sleep 2; [ -z "$PID" ] && PID=$(pgrep -f CassandraDaemon | head -1)
  grep -q "Starting listening for CQL clients" $R/stdout.txt 2>/dev/null && break; done
log "daemon pid $PID up"
grep -E "authenticator|authorizer|role_manager" $R/stdout.txt | grep -oE "(authenticator|authorizer|role_manager|network_authorizer)=[^;]*" | head -8
ok=0
for i in $(seq 1 45); do
  if R12_USER=cassandra R12_PASS=cassandra python3 -I $H/client.py --admin /dev/null > /dev/null 2>&1; then ok=1; break; fi; sleep 2; done
log "superuser login ok=$ok"
sed -e "s/@APW@/$APW/" -e "s/@VPW@/$VPW/" $H/admin1.cql.tmpl > $W/admin1.cql; chmod 600 $W/admin1.cql
R12_USER=cassandra R12_PASS=cassandra python3 -I $H/client.py --admin $W/admin1.cql > $R/admin1.txt 2>&1; log "admin1 rc=$?"
rm -f $W/admin1.cql
sleep 2
R12_USER=attacker R12_PASS=$APW python3 -I $H/client.py --admin $H/probe-attacker.cql > $R/probe-attacker.txt 2>&1; log "probe rc=$?"
R12_USER=attacker R12_PASS=$APW python3 -I $H/client.py --load --conns 8; log "attacker load rc=$?"
R12_USER=victim R12_PASS=$VPW python3 -I $H/client.py --victim-load; log "victim load rc=$?"
$T/bin/nodetool flush r12; $T/bin/nodetool flush vks; log flushed
$T/bin/nodetool compact r12; log compacted
$T/bin/nodetool tablestats r12.t | head -30
ls -l $T/data/data/r12/t-*/
$T/bin/nodetool drain; log drained
kill $PID; for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done; kill -0 $PID 2>/dev/null && kill -9 $PID
cp $T/logs/system.log $R/
rm -rf $T/logs
mkdir -p $W/seed
tar -C $T -cf $W/seed/data.tar data && ls -l $W/seed/data.tar
rm -rf $T/data
log "SEED done"
