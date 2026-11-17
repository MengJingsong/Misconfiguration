#!/usr/bin/env bash
# B8: gather small log excerpts from /mydata/b8/runs into /mydata/b8/excerpts (copied to the case's logs/).
cd /mydata/b8/runs; O=/mydata/b8/excerpts; rm -rf $O; mkdir -p $O
RUNS=$(ls -tr -d */ | tr -d /)
for r in $RUNS; do echo "######## $r"; cat $r/arm.log; done > $O/arm-outcomes.txt
python3 /mydata/b8/harness/summ.py $RUNS > $O/summary.txt 2>&1
for r in $RUNS; do for f in $r/replay/histo-*.txt; do [ -f $f ] || continue; echo "######## $f"; head -22 $f; \
  grep -E " org.apache.cassandra.db.(Mutation|partitions.PartitionUpdate|rows.BTreeRow|rows.BufferCell|rows.ArrayCell)$| org.apache.cassandra.concurrent.FutureTask$" $f; done; done > $O/replay-histograms.txt
for r in $RUNS; do for f in $r/dumps/hist-*.txt; do [ -f $f ] || continue; echo "######## $f"; head -16 $f; done; \
  for p in load replay; do grep -hE "java.lang.OutOfMemoryError|Dumping heap|Heap dump file" $r/$p/stdout.txt 2>/dev/null | sed "s|^|$r/$p: |" | head -6; \
  grep -hE "^ERROR.*OutOfMemory" $r/$p/system.log 2>/dev/null | head -2 | cut -c1-200 | sed "s|^|$r/$p: |"; done; done > $O/oom-evidence.txt
for r in $RUNS; do echo "######## $r"; grep -hE "Replaying|Finished reading|Log replay complete|Enqueuing flush of b8|Writing Memtable-t_" $r/replay/system.log 2>/dev/null | cut -c1-220; done > $O/replay-timelines.txt
for r in $RUNS; do echo "######## $r"; grep -h "Pause Full" $r/replay/gc.log* 2>/dev/null | cut -c1-200; done > $O/replay-full-gcs.txt
grep -h "JVM Arguments" cal1/replay/system.log | head -1 | tr ',' '\n' > $O/jvm-args-cal1-replay.txt
ls -la $O; du -sh /mydata/b8/runs
