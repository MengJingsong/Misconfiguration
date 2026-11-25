#!/usr/bin/env bash
# B25 Step A (3): reach known-answer check (design §2.5). Not a reading. Expected: reachable regions 22, R_s 10.
# usage: reach-check.sh [outdir]      (on the node; U jar and its lib jars on the classpath)
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd); W=/mydata/s4/b25; U=$W/cassandra-u; O=${1:-$W/logs/reachcheck}
mkdir -p "$O/cls"; rm -f "$O"/{ready,stop} "$O"/rc.hprof
CP="$U/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$U/build/lib/jars/*:$U/lib/*"
javac -nowarn -cp "$CP" -d "$O/cls" "$H/ReachCheck.java"
( setsid nohup systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0 java -Xmx1g -XX:+UseG1GC -XX:G1HeapRegionSize=16m \
    -cp "$O/cls:$CP" org.apache.cassandra.metrics.ReachCheck "$O/ready" "$O/stop" < /dev/null > "$O/java.out" 2>&1 & )
for i in $(seq 1 150); do [ -e "$O/ready" ] && break; sleep 0.2; done
[ -e "$O/ready" ] || { echo "ReachCheck did not start"; cat "$O/java.out"; exit 1; }
pid=$(pgrep -f "org.apache.cassandra.metrics.ReachCheck $O/ready" | head -1)
jcmd "$pid" GC.heap_dump "$O/rc.hprof" > /dev/null
touch "$O/stop"
t0=$(date +%s.%N)
python3 -I "$H/hprof_reach.py" "$O/rc.hprof" > "$O/reach.json"
t1=$(date +%s.%N)
python3 -I -c "
import json
r=json.load(open('$O/reach.json'))
ok = r['reachable']['regions']==22 and r['R_s']==10
print('reach check', 'ok' if ok else 'MISMATCH', 'reachable', r['reachable']['regions'], 'R_s', r['R_s'], 'regions_in_dump', r['regions_in_dump'],
      'cut_field_refs', r['sampler_cut_field_refs'], 'counted', r['reachable']['counted'], 'seconds', round($t1-$t0,2))
" | tee "$O/reach-check-summary.txt"
rm -f "$O/rc.hprof"
sleep 1; pgrep -f "org.apache.cassandra.metrics.ReachCheck" && echo "ReachCheck still running" || true
