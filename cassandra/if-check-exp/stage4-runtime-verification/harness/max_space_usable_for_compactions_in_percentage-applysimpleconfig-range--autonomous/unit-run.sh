#!/usr/bin/env bash
# Unit tier B2 of max_space_usable_for_compactions_in_percentage-applysimpleconfig-range--autonomous.
# usage (on the measured node): CASSANDRA_HOME=~/cassandra-run4 unit-run.sh [probe|control|all]    output: ~/s4b-logs/msu/unit/
#   probe    MaxSpaceRangeProbe, one fresh JVM per yaml value (-0.01 0 0.5 0.95 1 1.01), twice (drift); plus a "default" yaml with no entry
#   control  the closed positive control MaxCompactionSpaceOperandTest (budget = round((usable-minFree)*pct) at 1.0/0.95/0.5/0.0) via ant testsome
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run4}
L=$HOME/s4b-logs/msu/unit; mkdir -p "$L"; what=${1:-all}
CLOSED=$H/../max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--autonomous
cd "$C"
echo "unit-run $what $(date -Is) clone $C $(git describe --tags) harness md5 $(md5sum "$H/MaxSpaceRangeProbe.java" | cut -c1-12)" | tee -a "$L/summary.txt"
if [ "$what" = probe ] || [ "$what" = all ]; then
  rm -rf "$L/probe-cls"; mkdir -p "$L/probe-cls"
  CP="$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*"
  javac -cp "$CP" -d "$L/probe-cls" "$H/MaxSpaceRangeProbe.java" 2>&1 | tee "$L/javac.log"
  OPTS=$(grep -h '^--add' "$C/conf/jvm11-server.options" | tr '\n' ' ')
  for rep in 1 2; do
    for v in -0.01 0 0.5 0.95 1 1.01 default; do
      T=$L/work-$rep-$v; rm -rf "$T"; mkdir -p "$T"/{data,commitlog,saved_caches,hints,cdc_raw}
      cp "$C/conf/cassandra.yaml" "$T/cassandra.yaml"
      {
        echo "data_file_directories: [$T/data]"; echo "commitlog_directory: $T/commitlog"; echo "saved_caches_directory: $T/saved_caches"
        echo "hints_directory: $T/hints"; echo "cdc_raw_directory: $T/cdc_raw"
        [ "$v" != default ] && echo "max_space_usable_for_compactions_in_percentage: $v"
      } >> "$T/cassandra.yaml"
      java -Xmx1g $OPTS -Dcassandra.config=file://$T/cassandra.yaml -Dcassandra.storagedir=$T -Dcassandra.logdir=$T -cp "$L/probe-cls:$CP" MaxSpaceRangeProbe "v=$v rep=$rep" "$T/data" > "$L/probe-$rep-$v.out" 2>&1
      echo "probe rep=$rep v=$v exit=$? : $(grep -h 'PROBE result' "$L/probe-$rep-$v.out" | cut -c1-260)" | tee -a "$L/summary.txt"
      rm -rf "$T"
    done
  done
fi
if [ "$what" = control ] || [ "$what" = all ]; then
  cp "$CLOSED/MaxCompactionSpaceOperandTest.java" "$C/test/unit/org/apache/cassandra/db/"
  rm -f "$L/readings-control.txt"
  READINGS_OUT="$L/readings-control.txt" ant testsome -Dtest.name=org.apache.cassandra.db.MaxCompactionSpaceOperandTest > "$L/control.ant.log" 2>&1 < /dev/null
  echo "control exit=$? $(grep -m1 -o 'Tests run: [^<]*' "$L/control.ant.log") OK=$(grep -c 'READING OK' "$L/readings-control.txt") MISMATCH=$(grep -c 'MISMATCH' "$L/readings-control.txt")" | tee -a "$L/summary.txt"
  cp build/test/output/TEST-org.apache.cassandra.db.MaxCompactionSpaceOperandTest.xml "$L/" 2>/dev/null
  # upstream known answer for the build and for DirectoriesTest (the code under the control)
  ant testsome -Dtest.name=org.apache.cassandra.db.DirectoriesTest > "$L/directories.ant.log" 2>&1 < /dev/null
  echo "DirectoriesTest exit=$? $(grep -m1 -o 'Tests run: [^<]*' "$L/directories.ant.log")" | tee -a "$L/summary.txt"
fi
ps -eo cmd | grep '[C]assandraDaemon' || echo "no CassandraDaemon" | tee -a "$L/summary.txt"
