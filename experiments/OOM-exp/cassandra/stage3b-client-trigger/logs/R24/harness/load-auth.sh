#!/usr/bin/env bash
# 3-b R24 lifetime LOAD (not a reading), pc72 2026-11-24: auth on (conf-auth), n1 8G / n2 16G as stage 2's LOAD lifetime.
# Admin (superuser cassandra): system_auth RF 2 + repair, roles, r24.w2k (RF 2) and vks.kv (RF 2), grants. Probes (pre-auth frames,
# no credentials, attacker, nogrant, selonly). The ATTACKER role loads w2k (2,048 x 64 KiB, k = 0, CL ALL); the victim preloads vks.kv.
# Attacker / selonly single queries at 8 GiB (QUORUM F = 128; F = 4,096). No nodetool flush / compact: tablestats before the stop show
# what the server flushed on its own; the stop is the harness's drain + SIGTERM (a node restart), then template-n1|n2.
set -uo pipefail
ROOT=/mydata/s4/3b-R24; H=$ROOT/harness; V="bash $H/ctl.sh"; C="bash $H/client.sh"; R=$ROOT/runs/LOAD
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
as(){ local u=$1 p=$2; shift 2; JOPTS="-Dr24.user=$u -Dr24.pass=$p" XMX=-Xmx2g $C LOAD "$@"; }
$V prep LOAD LOAD || exit 1
$V start LOAD 1 8G auto && $V ready LOAD 1 || exit 1
$V start LOAD 2 16G auto && $V ready LOAD 2 || exit 1
$V ring LOAD || exit 1
for k in $(seq 1 30); do as cassandra cassandra cql 127.0.0.1 $H/probe-super.cql > $R/super-wait.txt 2>&1; grep -q '^OK' $R/super-wait.txt && break; sleep 3; done
log "superuser login: $(grep -c '^OK' $R/super-wait.txt) ok after $k tries"
as cassandra cassandra cql 127.0.0.1 $H/admin1.cql | tee $R/admin1.txt
for i in 1 2; do log "repair -full system_auth n$i"; $V nt $i repair -full system_auth 2>&1 | tail -3; done | tee $R/repair.txt
as cassandra cassandra cql 127.0.0.1 $H/admin2.cql | tee $R/admin2.txt
sleep 3
log "pre-auth frames"; python3 $H/preauth.py 127.0.0.1 2>&1 | tee $R/preauth.txt
log "driver without credentials"; XMX=-Xmx2g $C LOAD one 127.0.0.1 w2k QUORUM 128 1 2>&1 | grep -v '^SLF4J' | tee $R/noauth.txt
log "driver with a wrong password"; as attacker wrong-pw one 127.0.0.1 w2k QUORUM 128 1 2>&1 | grep -v '^SLF4J' | tee -a $R/noauth.txt
as attacker atk-r24-pw cql 127.0.0.1 $H/probe-attacker.cql | tee $R/probe-attacker.txt
as nogrant ng-r24-pw cql 127.0.0.1 $H/probe-nogrant.cql | tee $R/probe-nogrant.txt
as selonly sel-r24-pw cql 127.0.0.1 $H/probe-selonly.cql | tee $R/probe-selonly.txt
log "victim preload"; JOPTS="-Dr24.user=victim -Dr24.pass=vic-r24-pw" XMX=-Xmx2g CLS=R24Victim $C LOAD preload 127.0.0.1 10000 2>&1 | grep -v '^SLF4J' | tee $R/victim-preload.txt
log "attacker load w2k"; t0=$(date +%s); as attacker atk-r24-pw load 127.0.0.1 w2k 2048 65536 2>&1 | grep -v '^SLF4J' | tee $R/attacker-load.txt; log "load took $(( $(date +%s) - t0 )) s"
for i in 1 2; do echo "== n$i (before any stop; no flush/compact command)"; $V nt $i tablestats r24.w2k | grep -E "SSTable count|Space used \(live\)|Memtable cell count|Memtable data size|Number of partitions|Compacted partition maximum"; done | tee $R/tablestats-before-stop.txt
log "attacker single queries at 8 GiB"; as attacker atk-r24-pw one 127.0.0.1 w2k QUORUM 128 3 2>&1 | grep -v '^SLF4J' | tee $R/one-attacker.txt
TABLES=w2k $V rfpk LOAD after-attacker | tee $R/rfpk-after-attacker.txt
log "selonly single queries"; as selonly sel-r24-pw one 127.0.0.1 w2k QUORUM 128 2 2>&1 | grep -v '^SLF4J' | tee $R/one-selonly.txt
TABLES=w2k $V rfpk LOAD after-selonly | tee $R/rfpk-after-selonly.txt
log "attacker F=4096"; as attacker atk-r24-pw one 127.0.0.1 w2k QUORUM 4096 1 2>&1 | grep -v '^SLF4J' | tee $R/one-attacker-f4096.txt
grep -h 'Replica filtering protection\|Oversized\|cached over\|Unauthorized\|AuthenticationException' $R/n1/logs/system.log $R/n2/logs/system.log | cut -c1-400 | head -20 > $R/rfp-excerpt.txt
for i in 1 2; do echo "n$i hints: $(ls $ROOT/n$i/hints | wc -l)"; done
$V stop LOAD
for i in 1 2; do echo "n$i r24 Data.db after stop: $(ls $ROOT/n$i/data/r24/w2k-*/*-Data.db 2>/dev/null | wc -l) ($(du -cb $ROOT/n$i/data/r24/w2k-*/*-Data.db 2>/dev/null | tail -1 | cut -f1) B)"; done | tee $R/sstables-after-stop.txt
grep -c "OutOfMemoryError" $R/n1/logs/system.log $R/n2/logs/system.log
for i in 1 2; do rm -rf $ROOT/template-n$i; cp -a $ROOT/n$i $ROOT/template-n$i; rm -rf $ROOT/template-n$i/saved_caches/*; done
du -sh $ROOT/template-n1 $ROOT/template-n2
log "LOAD done"
