# C5 stage 2 shared paths (sourced on ms0604)
B=/mydata/s4/cassandra-base; ROOT=/mydata/s4/c5-w1; H=$ROOT/h; INST=$ROOT/inst; RUNS=$ROOT/runs; TPL=$ROOT/template
J=$B/build/lib/jars
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$B/build/classes/main:$B/lib/*"
NT="$B/bin/nodetool -h 127.0.0.1 -p 7299"
log(){ echo "[$(TZ=America/New_York date '+%F %T')] $*"; }
