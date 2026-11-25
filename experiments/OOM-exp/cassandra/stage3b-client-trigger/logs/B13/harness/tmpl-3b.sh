#!/usr/bin/env bash
# B13 3-b confirm (ms0611, 2026-11-24): LOAD lifetime (not a reading). Auth on. The superuser makes the roles, the admin
# schema and the grants; the admin (superuser) loads the stage-2 data (64 x 56 x 64 KiB over v4) and flushes/drains
# (admin steps, as stage 2's template); then the claim checks (privileges, pre-auth reply, response sizes) run as the
# roles. node/data -> tmpl/data (system_auth included, so every lifetime has the same roles and grants).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); ROOT=/mydata/s4/3b-B13; NODE=$ROOT/node; OUT=$ROOT/runs/LOAD; T=$ROOT/tree
IP=127.0.0.131
export BUILD=base XMX=2048M DIRECT=auto DUMP=0 CASSANDRA_HOME=$T
mkdir -p "$OUT"
log(){ echo "[$(TZ=America/New_York date '+%T')] $*"; }
su_cql(){ timeout 60 "$T/bin/cqlsh" $IP -u cassandra -p cassandra -e "$1"; }
as_cql(){ timeout 60 "$T/bin/cqlsh" $IP -u "$1" -p "$2" -e "$3"; }
"$H/ctl.sh" gen && "$H/ctl.sh" start || exit 1
for _ in $(seq 90); do grep -q "Starting listening for CQL clients" $NODE/logs/system.log 2>/dev/null && break; sleep 2; done
grep -q "Starting listening for CQL clients" $NODE/logs/system.log || { echo "START FAIL"; "$H/ctl.sh" stop; exit 1; }
cp $NODE/yaml.diff "$OUT/yaml.diff"
grep -m1 "Node configuration" $NODE/logs/system.log | grep -o "authenticator=[^;]*;\|authorizer=[^;]*;\|role_manager=[^;]*;\|network_authorizer=[^;]*;\|networking_cache_size=[^;]*;\|native_transport_max_threads=[^;]*;" > "$OUT/nodeconf.txt"
for _ in $(seq 40); do su_cql "SELECT role FROM system_auth.roles" > /dev/null 2>&1 && break; sleep 3; done
{
log "superuser setup (default role cassandra)"
su_cql "CREATE ROLE IF NOT EXISTS attacker WITH PASSWORD = 'atk-3b-B13' AND LOGIN = true AND SUPERUSER = false;
CREATE ROLE IF NOT EXISTS nogrant WITH PASSWORD = 'ng-3b-B13' AND LOGIN = true AND SUPERUSER = false;
CREATE ROLE IF NOT EXISTS tenant WITH PASSWORD = 'ten-3b-B13' AND LOGIN = true AND SUPERUSER = false;
CREATE KEYSPACE IF NOT EXISTS b13 WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE IF NOT EXISTS b13.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck));
CREATE KEYSPACE IF NOT EXISTS vic WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE IF NOT EXISTS vic.kv (k int PRIMARY KEY, v blob);
GRANT SELECT ON TABLE b13.t TO attacker;
GRANT SELECT ON TABLE vic.kv TO tenant;
GRANT MODIFY ON TABLE vic.kv TO tenant;"
su_cql "LIST ROLES; LIST ALL PERMISSIONS OF attacker; LIST ALL PERMISSIONS OF nogrant; LIST ALL PERMISSIONS OF tenant;"
} > "$OUT/admin-setup.txt" 2>&1
cat "$OUT/admin-setup.txt"
log "admin load (superuser, v4)"
LOAD_JOPTS="-Db13.user=cassandra -Db13.pass=cassandra" "$H/jv.sh" load $IP 2>&1 | tail -2 | tee "$OUT/admin-load.txt"
NT=$T/bin/nodetool
{ CASSANDRA_CONF=$NODE/conf $NT -h 127.0.0.1 -p 7313 flush b13 && CASSANDRA_CONF=$NODE/conf $NT -h 127.0.0.1 -p 7313 tablestats b13.t | grep -E "SSTable count|Space used \(live\)|Number of partitions"; } | tee -a "$OUT/admin-load.txt"
{
log "privilege checks"
echo "== attacker (expected: SELECT b13.t ok; everything else Unauthorized)"
as_cql attacker atk-3b-B13 "SELECT pk, ck FROM b13.t WHERE pk = 0 LIMIT 2;" 2>&1 | tail -4
as_cql attacker atk-3b-B13 "INSERT INTO b13.t (pk, ck, v) VALUES (0, 999, 0x00);" 2>&1 | tail -1
as_cql attacker atk-3b-B13 "SELECT * FROM vic.kv LIMIT 1;" 2>&1 | tail -1
as_cql attacker atk-3b-B13 "CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1};" 2>&1 | tail -1
as_cql attacker atk-3b-B13 "ALTER TABLE b13.t WITH comment = 'x';" 2>&1 | tail -1
as_cql attacker atk-3b-B13 "SELECT role FROM system_auth.roles;" 2>&1 | tail -1
echo "== nogrant (expected: b13.t and vic.kv Unauthorized; system_schema / system.local readable)"
as_cql nogrant ng-3b-B13 "SELECT pk FROM b13.t WHERE pk = 0 LIMIT 1;" 2>&1 | tail -1
as_cql nogrant ng-3b-B13 "SELECT * FROM vic.kv LIMIT 1;" 2>&1 | tail -1
as_cql nogrant ng-3b-B13 "CREATE KEYSPACE ng WITH replication = {'class':'SimpleStrategy','replication_factor':1};" 2>&1 | tail -1
as_cql nogrant ng-3b-B13 "SELECT count(*) FROM system_schema.columns;" 2>&1 | tail -4
as_cql nogrant ng-3b-B13 "SELECT count(*) FROM system_schema.tables;" 2>&1 | tail -4
as_cql nogrant ng-3b-B13 "SELECT release_version FROM system.local;" 2>&1 | tail -4
echo "== tenant (expected: b13.t Unauthorized; vic.kv ok)"
as_cql tenant ten-3b-B13 "SELECT pk FROM b13.t WHERE pk = 0 LIMIT 1;" 2>&1 | tail -1
as_cql tenant ten-3b-B13 "INSERT INTO vic.kv (k, v) VALUES (0, 0x00); SELECT k FROM vic.kv LIMIT 1;" 2>&1 | tail -4
} > "$OUT/authcheck.txt" 2>&1
cat "$OUT/authcheck.txt"
log "pre-auth check (v5)"
taskset -c 6-7 python3 "$H/preauth5.py" $IP 3 "SELECT v FROM b13.t WHERE pk = 0" > "$OUT/preauth.txt" 2>&1
taskset -c 6-7 python3 "$H/preauth5.py" $IP 2 "SELECT * FROM system_schema.columns" >> "$OUT/preauth.txt" 2>&1
cat "$OUT/preauth.txt"
log "response sizes (v5, one unpaged request, drained)"
rs(){ local tag=$1; shift; rm -f $OUT/rs.stop; ( env "$@" taskset -c 6-7 python3 "$H/stall5.py" $IP 1 1 1 1 drain $OUT/rs.stop > $OUT/rs-$tag.log 2>&1 & ); sleep 6; touch $OUT/rs.stop; sleep 2; echo "$tag: $(grep -E 'READY|REQ_BYTES|CLOSED' $OUT/rs-$tag.log | tr '\n' ' ')"; }
{
rs attacker-b13t B13_USER=attacker B13_PASS=atk-3b-B13
rs nogrant-columns B13_USER=nogrant B13_PASS=ng-3b-B13 "B13_QUERY=SELECT * FROM system_schema.columns"
rs nogrant-tables B13_USER=nogrant B13_PASS=ng-3b-B13 "B13_QUERY=SELECT * FROM system_schema.tables"
rs nogrant-b13t B13_USER=nogrant B13_PASS=ng-3b-B13
} > "$OUT/response-sizes.txt" 2>&1
cat "$OUT/response-sizes.txt"
CASSANDRA_CONF=$NODE/conf $NT -h 127.0.0.1 -p 7313 drain
"$H/ctl.sh" stop
grep -c " ERROR " $NODE/logs/system.log > "$OUT/error-count.txt"; cp $NODE/logs/system.log "$OUT/system.log"
rm -rf $ROOT/tmpl; mkdir -p $ROOT/tmpl; cp -a $NODE/data $ROOT/tmpl/data; du -sh $ROOT/tmpl/data
echo TMPL DONE
