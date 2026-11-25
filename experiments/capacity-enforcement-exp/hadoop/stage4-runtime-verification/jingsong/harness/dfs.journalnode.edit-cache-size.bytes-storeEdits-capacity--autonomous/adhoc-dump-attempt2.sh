#!/usr/bin/env bash
R=/mydata/jingsong-s4/dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity-run1
for kr in K4:120 K5:250; do K=${kr%%:*}; N=${kr##*:}
  until [ -f $R/cluster/$K/cluster-run.log ] && grep -q "rounds done: $N$" $R/cluster/$K/cluster-run.log; do sleep 2; done
  P=$(cat $R/cluster/$K/pid/jn/*.pid)
  { date -u +%FT%TZ; /usr/lib/jvm/java-8-openjdk-amd64/bin/jcmd $P GC.heap_dump $R/cluster/$K-heap.hprof; date -u +%FT%TZ; } > $R/cluster/$K-heapdump.txt 2>&1
done
