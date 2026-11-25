#!/usr/bin/env bash
# C8 stage 3-b confirm (2026-11-24): LOAD lifetime. Usage: load-life.sh <run-id>
# Fresh node at the attack budget (1,536 / 768 MiB, auth on). Superuser creates the roles and the victim's schema; the
# attacker (GRANT CREATE ON ALL KEYSPACES only) creates c8 / c8.big and the stress schema keyspace1.standard1 and loads
# 2,000,000 distinct 32-character values over CQL. NO nodetool flush / compact, no seed copy: the sstable layout is what
# the server's own flushes and STCS compactions make. The observer waits for compactions to settle (nodetool
# compactionstats, observation only), records the layout, then `nodetool drain` (flushes the memtable remainder, which
# CREATE INDEX's own forceBlockingFlush would also do) and stops the node; data/ (without saved_caches) becomes $TPL.
set -u
. $(dirname "$0")/common.sh
RID=$1; R=$W/runs/$RID; mkdir -p $R; exec >> $R/driver.txt 2>&1
log "LOAD lifetime $RID heap=$HEAP direct=$DIRECT"
precheck
rm -rf $T/data $T/logs
start_node $RID $R
for i in $(seq 1 45); do CQ -u cassandra -p cassandra -e "LIST ROLES" > /dev/null 2>&1 && break; sleep 2; done
{
  S="CREATE ROLE attacker WITH PASSWORD = '$APW' AND LOGIN = true AND SUPERUSER = false;
GRANT CREATE ON ALL KEYSPACES TO attacker;
CREATE ROLE nogrant WITH PASSWORD = 'nogrant-pw-3b' AND LOGIN = true AND SUPERUSER = false;
CREATE ROLE victim WITH PASSWORD = '$VPW' AND LOGIN = true AND SUPERUSER = false;
CREATE KEYSPACE victim WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE victim.kv (k int PRIMARY KEY, v text);
GRANT SELECT ON TABLE victim.kv TO victim;
GRANT MODIFY ON TABLE victim.kv TO victim;"
  echo "== superuser statements (cqlsh as cassandra)"; echo "$S"
  CQ -u cassandra -p cassandra -e "$S" && echo "== setup OK"
  echo "== LIST ROLES"; CQ -u cassandra -p cassandra -e "LIST ROLES"
  for r in attacker victim nogrant; do echo "== LIST ALL PERMISSIONS OF $r (before attacker DDL)"; CQ -u cassandra -p cassandra -e "LIST ALL PERMISSIONS OF $r"; done
  echo "== attacker negative checks (expect Unauthorized)"
  CQ -u attacker -p $APW -e "SELECT * FROM victim.kv LIMIT 1" 2>&1 | tail -1
  CQ -u attacker -p $APW -e "ALTER TABLE victim.kv WITH comment = 'x'" 2>&1 | tail -1
  CQ -u attacker -p $APW -e "CREATE INDEX vi ON victim.kv (v) USING 'sai'" 2>&1 | tail -1
  echo "== nogrant negative checks (expect Unauthorized)"
  CQ -u nogrant -p nogrant-pw-3b -e "CREATE KEYSPACE ng WITH replication = {'class':'SimpleStrategy','replication_factor':1}" 2>&1 | tail -1
  echo "== unauthenticated cqlsh (expect AuthenticationFailed)"; CQ -e "SELECT now() FROM system.local" 2>&1 | tail -1
  echo "== attacker DDL (cqlsh as attacker)"
  CQ -u attacker -p $APW -e "CREATE KEYSPACE c8 WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE c8.big (pk bigint PRIMARY KEY, v text);" && echo "== attacker DDL OK"
  echo "== LIST ALL PERMISSIONS OF attacker (after DDL; creator auto-grants)"; CQ -u cassandra -p cassandra -e "LIST ALL PERMISSIONS OF attacker"
} > $R/auth-setup.txt 2>&1
grep -q "== setup OK" $R/auth-setup.txt && grep -q "== attacker DDL OK" $R/auth-setup.txt || { log "INVALID: setup failed"; stop_node $RID; exit 1; }
log "auth setup + attacker DDL done"
log "attacker: stress schema (cassandra-stress write n=1000 as attacker)"
timeout 300 $T/tools/bin/cassandra-stress write n=1000 cl=ONE -schema 'replication(factor=1)' -node 127.0.0.1 \
  -mode native cql3 user=attacker password=$APW > $R/stress-schema.log 2>&1; log "stress schema rc=$?"
monitors $PID $R $R/STOP
log "attacker load start at_ms $(ems)"
python3 -I $H/load3b.py --user attacker --pw $APW --rows 2000000 --procs 4 --conc 64 --log $R/load.log > $R/load.out 2>&1
log "attacker load end rc=$? at_ms $(ems): $(tail -1 $R/load.out)"
# observer only: wait for the server's own compactions to settle (<= 15 min)
for i in $(seq 1 90); do
  cs=$(NT compactionstats 2>&1); echo "$(date +%T) $(echo "$cs" | tr '\n' '|')" >> $R/compactionstats.txt
  echo "$cs" | grep -qE "pending tasks:? +0( |$)" && ! echo "$cs" | grep -qiE "^ *[0-9a-f-]{36}|Compaction +c8" && break
  sleep 10
done
log "compactions settled (or 15 min cap) after $((i*10)) s"
ls -l $T/data/data/c8/big-*/*-Data.db > $R/sstables-before-drain.txt 2>&1
NT tablestats c8.big > $R/tablestats-before-drain.txt 2>&1
log "count check (attacker): $(CQT=600 CQ -u attacker -p $APW --request-timeout=600 -e 'SELECT count(*) FROM c8.big' 2>&1 | tr '\n' ' ' | tr -s ' ')"
stop_monitors $R
NTT=300 NT drain; log "drain rc=$?"
stop_node $RID
ls -l $T/data/data/c8/big-*/*-Data.db > $R/sstables-after-drain.txt 2>&1
for f in $T/data/data/c8/big-*/*-Data.db; do echo "== $f"; $T/tools/bin/sstablemetadata $f 2>/dev/null | grep -E "Estimated partitions|totalRows|SSTable Level|Repaired at|Compressor|Minimum timestamp|Maximum timestamp" ; done > $R/sstablemetadata.txt 2>&1
rm -rf $TPL; mkdir -p $TPL; cp -a $T/data/. $TPL/; rm -rf $TPL/saved_caches
du -sh $TPL > $R/template-du.txt
cp $T/logs/system.log* $T/logs/debug.log* $T/logs/gc.log* $R/ 2>/dev/null
log "LOAD done"
