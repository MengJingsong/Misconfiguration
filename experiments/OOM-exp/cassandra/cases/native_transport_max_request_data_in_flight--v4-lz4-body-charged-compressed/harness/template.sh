#!/usr/bin/env bash
# Build the data template: empty node at 2048M, schema, load <rows>, flush, drain, stop, copy to template/.
#   template.sh <rows>   (log: /mydata/s4/B19/template.log)
set -uo pipefail
H=/mydata/s4/B19/h; ROOT=/mydata/s4/B19; NODE=$ROOT/node; ROWS=${1:-1000000}
echo "$(TZ=America/New_York date +%T) template rows=$ROWS"
NOTEMPLATE=1 "$H/ctl.sh" gen || exit 1
XMX=2048M DUMP=0 "$H/ctl.sh" start
for _ in $(seq 90); do grep -q "Starting listening for CQL clients" $NODE/logs/system.log 2>/dev/null && break; sleep 2; done
"$H/cli.sh" schema
"$H/cli.sh" load $ROWS
taskset -c 6-7 /mydata/s4/cassandra-base/bin/nodetool -h 127.0.0.1 -p 7319 flush b19
taskset -c 6-7 /mydata/s4/cassandra-base/bin/nodetool -h 127.0.0.1 -p 7319 drain
"$H/ctl.sh" stop
rm -rf $ROOT/template; mkdir -p $ROOT/template
cp -a $NODE/data $NODE/commitlog $NODE/hints $NODE/saved_caches $ROOT/template/
du -sh $ROOT/template; ls $ROOT/template/data/b19/
echo "$(TZ=America/New_York date +%T) TEMPLATE_DONE"
