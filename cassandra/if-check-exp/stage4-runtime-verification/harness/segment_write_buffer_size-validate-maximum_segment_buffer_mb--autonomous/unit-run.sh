#!/usr/bin/env bash
# Unit tier B2 of segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous.
# usage (on the measured node): unit-run.sh [stock|patched|upstream|all]    output: ~/s4b-logs/sai/unit/
#   stock     SaiBufferProbe, a fresh JVM per yaml value, twice, clone ~/cassandra-run4 (stock source)
#   patched   the same with MAXIMUM_SEGMENT_BUFFER_MB = 2048 in a fresh copy ~/cassandra-run5 (made with copy-source.sh, built with `ant jar`)
#   upstream  upstream StorageAttachedIndexOptionsTest in ~/cassandra-run4 (known answer)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
L=$HOME/s4b-logs/sai/unit; mkdir -p "$L"; what=${1:-all}
echo "unit-run $what $(date -Is) harness md5 $(md5sum "$H/SaiBufferProbe.java" | cut -c1-12)" | tee -a "$L/summary.txt"
probe() {  # probe <clone> <tag> <values...>
  local C=$1 tag=$2; shift 2
  local CP="$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*"
  rm -rf "$L/cls-$tag"; mkdir -p "$L/cls-$tag"
  javac -cp "$CP" -d "$L/cls-$tag" "$H/SaiBufferProbe.java" 2>&1 | tee "$L/javac-$tag.log"
  local OPTS; OPTS=$(grep -h '^--add' "$C/conf/jvm11-server.options" | tr '\n' ' ')
  for rep in 1 2; do
    for v in "$@"; do
      local T=$L/work-$tag-$rep-$v; rm -rf "$T"; mkdir -p "$T"/{data,commitlog,saved_caches,hints,cdc_raw}
      cp "$C/conf/cassandra.yaml" "$T/cassandra.yaml"
      { echo "data_file_directories: [$T/data]"; echo "commitlog_directory: $T/commitlog"; echo "saved_caches_directory: $T/saved_caches"
        echo "hints_directory: $T/hints"; echo "cdc_raw_directory: $T/cdc_raw"
        [ "$v" != default ] && printf 'sai_options:\n  segment_write_buffer_size: %sMiB\n' "$v"; } >> "$T/cassandra.yaml"
      java -Xmx2g $OPTS -Dcassandra.config=file://$T/cassandra.yaml -Dcassandra.storagedir=$T -Dcassandra.logdir=$T -cp "$L/cls-$tag:$CP" SaiBufferProbe "$tag v=$v rep=$rep" > "$L/probe-$tag-$rep-$v.out" 2>&1
      echo "probe $tag rep=$rep v=$v exit=$? : $(grep -h 'PROBE result\|PROBE flip\|PROBE SEGMENT' "$L/probe-$tag-$rep-$v.out" | cut -c1-240 | tr '\n' '|')" | tee -a "$L/summary.txt"
      rm -rf "$T"
    done
  done
}
if [ "$what" = stock ] || [ "$what" = all ]; then probe $HOME/cassandra-run4 stock default 1 64 1024 4096 32768 32769 0; fi
if [ "$what" = patched ] || [ "$what" = all ]; then probe $HOME/cassandra-run5 patched 1024 2048 2049 32768; fi
if [ "$what" = upstream ] || [ "$what" = all ]; then
  cd $HOME/cassandra-run4
  ant testsome -Dtest.name=org.apache.cassandra.config.StorageAttachedIndexOptionsTest > "$L/upstream.ant.log" 2>&1 < /dev/null
  echo "upstream StorageAttachedIndexOptionsTest exit=$? $(grep -m1 -o 'Tests run: [^<]*' "$L/upstream.ant.log")" | tee -a "$L/summary.txt"
fi
ps -eo cmd | grep '[C]assandraDaemon' || echo "no CassandraDaemon" | tee -a "$L/summary.txt"
