# Sourced by unit-run.sh / cluster-run.sh on the run node (o115, stage 4, Jingsong).
# Case: default_buffer_size_in_mib_for_unsorted-build-maxsstablesizeinmib--autonomous
S4=/mydata/jingsong-cass-s4/o115
SRC=$S4/src
OUTD=$S4/out
CP="$S4/harness/classes:$SRC/build/classes/main:$SRC/build/lib/jars/*:$SRC/lib/*"
# B2i.7: the active lines of conf/jvm11-clients.options, as Cassandra's client scripts pass them
JOPTS=$(grep -v '^[[:space:]]*#' "$SRC/conf/jvm11-clients.options" | grep -v '^[[:space:]]*$' | tr '\n' ' ')
LOGBACK="-Dlogback.configurationFile=$SRC/conf/logback-tools.xml"
MAIN=org.apache.cassandra.io.sstable.BufferCapProbe

# unit tier prefix (B2a RUN): probe_unit <Xmx> <args...>
probe_unit() { local xmx=$1; shift; java -Xmx$xmx -XX:+ExitOnOutOfMemoryError $JOPTS $LOGBACK -cp "$CP" $MAIN "$@"; }
# cluster tier writer JVM (B3a): probe_cluster <Xmx> <gclog> <args...>
probe_cluster() { local xmx=$1 gcl=$2; shift 2; java -Xmx$xmx -XX:+UseG1GC -XX:+ExitOnOutOfMemoryError -Xlog:gc:file=$gcl $JOPTS $LOGBACK -cp "$CP" $MAIN "$@"; }

no_strays() {
  local p
  p=$(ps -eo pid,cmd | grep -E '[B]ufferCapProbe|[C]assandraDaemon' || true)
  if [ -n "$p" ]; then echo "STRAY PROCESSES: $p"; return 1; fi
  echo "no BufferCapProbe/CassandraDaemon running"
}
