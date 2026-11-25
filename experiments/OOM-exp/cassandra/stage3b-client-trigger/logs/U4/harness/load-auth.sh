#!/usr/bin/env bash
# 3-b confirm U4 lifetime LOAD (heap 8G as stage 2's LOAD; not a reading), auth on. Admin (default superuser) creates the
# schema and roles; the ATTACKER role (SELECT + MODIFY on u4.t only) loads 16 x 5,000 x 49,152 B; probes; victim preload;
# harness mechanics (flush, major compaction, drain, stop) as stage 2; then the template every attack lifetime clones.
set -uo pipefail
ROOT=/mydata/s4/3b-U4; H=$ROOT/harness; V="bash $H/node-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
R=$ROOT/runs/LOAD; O=$ROOT/logs/LOAD; mkdir -p $O
cl(){ bash $H/client.sh "$@"; }
$V start LOAD LOAD 8G auto && $V ready LOAD || exit 1
cp $R/yaml.diff $O/; cp $R/run.meta $O/
for i in $(seq 1 30); do U4USER=cassandra U4PASS=cassandra cl LOAD-ping U4Load cql 127.0.0.1 $H/ping.cql > $O/ping.txt 2>&1 && grep -q '^OK' $O/ping.txt && break; sleep 3; done
cat $O/ping.txt
U4USER=cassandra U4PASS=cassandra cl LOAD-admin U4Load cql 127.0.0.1 $H/admin.cql > $O/admin.txt 2>&1; cat $O/admin.txt
sleep 3
{ U4USER=attacker U4PASS=att-pw cl LOAD-pa U4Load cql 127.0.0.1 $H/probe-attacker.cql
  U4USER=reader U4PASS=rd-pw cl LOAD-pr U4Load cql 127.0.0.1 $H/probe-reader.cql
  U4USER=nogrant U4PASS=ng-pw cl LOAD-pn U4Load cql 127.0.0.1 $H/probe-nogrant.cql
  echo "== no credentials"; cl LOAD-px U4Load cql 127.0.0.1 $H/ping.cql
  echo "== wrong password"; U4USER=attacker U4PASS=wrong cl LOAD-pw U4Load cql 127.0.0.1 $H/ping.cql
  echo "== pre-auth hand-made frames"; python3 $H/preauth.py 127.0.0.1; } > $O/probes.txt 2>&1
grep -v '^\s*$' $O/probes.txt | cut -c1-260
echo "== attacker load $(date)"
( time U4USER=attacker U4PASS=att-pw cl LOAD-load U4Load load 127.0.0.1 16 5000 49152 0 ) > $O/load.out 2>&1
grep -c 'load err' $O/load.out; grep -v 'load err' $O/load.out | tail -5
U4USER=victim U4PASS=vic-pw cl LOAD-vp U4Victim preload 127.0.0.1 10000 > $O/victim-preload.txt 2>&1; cat $O/victim-preload.txt
$NT flush; time $NT compact u4
{ for pk in $(seq 0 15); do U4USER=attacker U4PASS=att-pw cl LOAD-one U4Load one 127.0.0.1 $pk 5000; done
  U4USER=reader U4PASS=rd-pw cl LOAD-one-r U4Load one 127.0.0.1 3 5000; } > $O/verify.txt 2>&1; cat $O/verify.txt
$NT tablestats u4.t | grep -E "SSTable count|Space used \(live\)|Compacted partition (maximum|mean)|Number of partitions" > $O/tablestats.txt; cat $O/tablestats.txt
$V stop LOAD
grep -c "OutOfMemoryError" $R/logs/system.log
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template | tee $O/template.du
echo LOAD-END
