#!/usr/bin/env bash
# C7 one run (design §2.5 Step C). Runs on the controller (pc node), drives ms0625 (n1, n3) and ms0640 (n2, n4) by ssh.
#   run.sh <run-id> <arm: C|T|I|S> <D MiB> <T tables>
# Clean start of all 4 instances, n1 with heap 2048M / direct D (I: concurrent_merkle_tree_requests=1 on n1 only),
# read-back, samplers, `timeout 1200 nodetool repair --full c7 standard1 s001..s(T-1)` from ms0625, wait for
# n1 death / repair end / 20 min, collect, stop all.
set -uo pipefail
RID=$1 ARM=$2 D=$3 T=$4
W=/mydata/s4/c7-w3; H=$W/h; R=$W/runs/$RID; NT="/mydata/s4/cassandra-base/bin/nodetool"
log(){ echo "[$(TZ=America/New_York date '+%T')] $*"; }
a(){ ssh ms0625 "$@"; }; b(){ ssh ms0640 "$@"; }
tables="standard1"; for i in $(seq 1 $((T-1))); do tables="$tables $(printf 's%03d' $i)"; done
log "run $RID arm=$ARM D=$D T=$T"
# 1. stop all, clear n1 logs/dumps/commitlog; peers' logs (per-run counts)
a "$H/ctl.sh stop n1 & $H/ctl.sh stop n3 & wait" ; b "$H/ctl.sh stop n2 & $H/ctl.sh stop n4 & wait"
a "rm -rf $W/inst/n1/logs/* $W/inst/n1/dumps/* $W/inst/n1/commitlog/* $W/inst/n3/logs/*; mkdir -p $R"
b "rm -rf $W/inst/n2/logs/* $W/inst/n4/logs/*"
# 2. arm yaml on n1, start n1 then peers in parallel
if [ "$ARM" = I ]; then a "$H/ctl.sh gen n1 concurrent_merkle_tree_requests=1"; else a "$H/ctl.sh gen n1"; fi
a "cp $W/inst/n1/yaml.diff $R/n1-yaml.diff; echo '$RID $ARM D=$D T=$T' > $R/argline; stat -c %h $W/inst/n1/data/c7/standard1-*/nb-*-big-Data.db > $R/linkcount.txt 2>&1"
a "DIRECT=$D $H/ctl.sh start n1"
for i in $(seq 40); do sleep 5; a "grep -q 'Startup complete' $W/inst/n1/logs/system.log 2>/dev/null" && break; done
a "$H/ctl.sh start n3" & b "$H/ctl.sh start n2" & b "$H/ctl.sh start n4" & wait
for i in $(seq 60); do sleep 5; n=$(a "$NT -h 127.0.0.1 -p 7199 status 2>/dev/null | grep -cE '^UN '"); [ "$n" = 4 ] && break; done
log "UN=$n"; [ "$n" = 4 ] || { log "INVALID: not all UN"; echo invalid-notUN > /dev/null; }
for i in $(seq 30); do
  p=$( { a "$NT -h 127.0.0.1 -p 7199 compactionstats; $NT -h 127.0.0.1 -p 7299 compactionstats"; b "$NT -h 127.0.0.1 -p 7199 compactionstats; $NT -h 127.0.0.1 -p 7299 compactionstats"; } 2>/dev/null | awk '/pending tasks/{s+=$3} END{print s+0}')
  [ "$p" = 0 ] && break; sleep 5; done
log "pending compactions=$p; idle 60 s"; sleep 60
# 3. read back
a "cd $R; java -cp $W/cls C7Sample get 7199 org.apache.cassandra.db:type=RepairService RepairSessionSpaceInMiB ConcurrentMerkleTreeRequests > readback.txt;
   $NT -h 127.0.0.1 -p 7199 getconcurrentcompactors >> readback.txt 2>&1;
   grep -o 'use_offheap_merkle_trees=[a-z]*\|concurrent_validations=[0-9-]*\|concurrent_merkle_tree_requests=[0-9]*\|repair_session_space=[a-z0-9]*' $W/inst/n1/logs/system.log | head -4 >> readback.txt;
   P=\$($H/ctl.sh pid n1); jcmd \$P VM.flags | tr ' ' '\n' | grep -E 'MaxDirectMemorySize|MaxHeapSize|UseG1GC' >> readback.txt; tr '\0' '\n' < /proc/\$P/cmdline > n1-cmdline.txt;
   $NT -h 127.0.0.1 -p 7199 status > status.txt; $NT -h 127.0.0.1 -p 7199 tablestats c7.standard1 c7.s149 | grep -E 'Table:|SSTable count|Number of partitions' >> readback.txt; $NT -h 127.0.0.1 -p 7199 ring > ring.txt; cat readback.txt"
# 4. samplers + repair
a "cd $R; P=\$($H/ctl.sh pid n1); CG=\$($H/ctl.sh cg n1); echo \"vpid=\$P cg=\$CG\" >> args.txt
   ( setsid nohup java -Xmx128m -cp $W/cls C7Sample 7199 1000 $R < /dev/null > sampler.err 2>&1 & echo \$! > .samp.pid )
   ( setsid nohup bash -c \"echo epoch_ms,mem_current,anon,rss_anon_kB,oom,oom_kill > $R/cg.csv; while kill -0 \$P 2>/dev/null; do echo \\\$(date +%s%3N),\\\$(cat \$CG/memory.current 2>/dev/null),\\\$(awk '/^anon /{print \\\$2}' \$CG/memory.stat 2>/dev/null),\\\$(awk '/^RssAnon/{print \\\$2}' /proc/\$P/status 2>/dev/null),\\\$(awk '/^oom /{print \\\$2}' \$CG/memory.events 2>/dev/null),\\\$(awk '/^oom_kill /{print \\\$2}' \$CG/memory.events 2>/dev/null) >> $R/cg.csv; cp \$CG/memory.events $R/memory.events.final 2>/dev/null; sleep 1; done\" < /dev/null > /dev/null 2>&1 & )
   sleep 3
   ( setsid nohup bash -c \"echo \\\$(date +%s%3N) repair start >> $R/args.txt; timeout 1200 $NT -h 127.0.0.1 -p 7199 repair --full c7 $tables > $R/repair.log 2>&1; echo \\\$? > $R/repair.exit; echo \\\$(date +%s%3N) repair end >> $R/args.txt\" < /dev/null > /dev/null 2>&1 & )"
log "repair started"
# 5. wait: n1 dead, repair ended, or 21 min
for i in $(seq 252); do sleep 5
  st=$(a "test -f $R/repair.exit && echo done; kill -0 \$(grep -o 'vpid=[0-9]*' $R/args.txt | head -1 | cut -d= -f2) 2>/dev/null || echo dead")
  case "$st" in *done*|*dead*) break ;; esac; done
log "end condition: [$st]"; sleep 5
# collect
a "cd $R; P=\$(grep -o 'vpid=[0-9]*' args.txt | head -1 | cut -d= -f2)
   for i in \$(seq 60); do kill -0 \$P 2>/dev/null || break; ls $W/inst/n1/dumps/*.hprof >/dev/null 2>&1 || break; sleep 3; done
   kill \$(cat .samp.pid) 2>/dev/null; rm -f .samp.pid
   mkdir -p n1-logs; cp -p $W/inst/n1/logs/system.log $W/inst/n1/logs/debug.log $W/inst/n1/logs/gc.log* $W/inst/n1/logs/hs_err* n1-logs/ 2>/dev/null
   kill -0 \$P 2>/dev/null && echo n1=alive > outcome.txt || echo n1=DEAD > outcome.txt
   echo repair_exit=\$(cat repair.exit 2>/dev/null) >> outcome.txt
   grep -v 'JVM Arguments' n1-logs/system.log | grep -n -m1 -B3 -A40 'OutOfMemoryError' > first-oom.txt 2>/dev/null
   echo direct_oom_lines=\$(grep -c 'OutOfMemoryError: Direct buffer memory\|OutOfMemoryError: Cannot reserve' n1-logs/system.log) >> outcome.txt
   echo heap_oom_lines=\$(grep -c 'OutOfMemoryError: Java heap' n1-logs/system.log) >> outcome.txt
   ls -la $W/inst/n1/dumps/ >> outcome.txt 2>&1; mv $W/inst/n1/dumps/*.hprof $R/ 2>/dev/null
   grep -h 'Created .* merkle trees with merkle trees size' $W/inst/n3/logs/debug.log > n3-trees.txt 2>/dev/null; cat outcome.txt"
b "grep -h 'Created .* merkle trees with merkle trees size' $W/inst/n2/logs/debug.log" > /tmp/c7-$RID-n2.txt 2>/dev/null; b "grep -h 'Created .* merkle trees with merkle trees size' $W/inst/n4/logs/debug.log" > /tmp/c7-$RID-n4.txt 2>/dev/null
scp -q /tmp/c7-$RID-n2.txt ms0625:$R/n2-trees.txt; scp -q /tmp/c7-$RID-n4.txt ms0625:$R/n4-trees.txt; rm -f /tmp/c7-$RID-n?.txt
for n in n2 n4; do b "grep -m3 -h 'ERROR\|OutOfMemory' $W/inst/$n/logs/system.log" | sed "s/^/$n: /"; done > /dev/null
# stop all
a "$H/ctl.sh stop n1 & $H/ctl.sh stop n3 & wait"; b "$H/ctl.sh stop n2 & $H/ctl.sh stop n4 & wait"
log "run $RID done"
