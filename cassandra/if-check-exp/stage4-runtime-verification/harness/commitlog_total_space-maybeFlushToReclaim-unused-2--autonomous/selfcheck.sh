#!/bin/bash
# Independent self-check (results §5) for commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.
# Re-derives the readings with awk/grep/zcat from the raw files, without the analysis scripts or reasons.txt/counts.txt.
# Usage: bash selfcheck.sh <run1 dir>
R=${1:?}; U=$R/unit; C=$R/cluster; M=1048576
echo "== unit: peak / settled-at-end / min, from cap.csv; COMMITLOG_DIRTY and MEMTABLE_* lines from the raw test-log tree"
for a in T3-s20 T4-s20 T8-s20 T1024-s20 T4-s0 T1024-s0 M M-nobreak; do
  awk -F, -v a=$a -v M=$M 'NR>1 && NF==6 {if($3>pk)pk=$3; last=$3; if($5-$3>dd)dd=$5-$3; if($3-$5>dd)dd=$3-$5; n++}
       END{printf "%-10s samples=%d peak=%.0fMiB last=%.0fMiB max|dir-counter|=%.0fMiB ", a, n, pk/M, last/M, dd/M}' $U/$a/cap.csv
  echo "CLD=$(find $U/$a/testlogs -type f | xargs zcat -f | grep -c 'Enqueuing flush of CLCap\..*Reason: COMMITLOG_DIRTY') ML=$(find $U/$a/testlogs -type f | xargs zcat -f | grep -c 'Enqueuing flush of CLCap\..*Reason: MEMTABLE_') junitOK=$(grep -c 'errors="0" failures="0"' $U/$a/TEST-*.xml)"
done
echo "== unit B2i: from the Byteman trace"
for a in M M-nobreak; do
  awk -v a=$a '/^SELECT/{s++; for(i=1;i<=NF;i++){split($i,kv,"="); v[kv[1]]=kv[2]}; if(v["gap"]>0)g++; if(v["stop259"]=="true"&&v["minimal"]=="true")m++; if(v["allocId"]!=v["allocIdAtCheck"])c++; ks=ks v["k"] "/" v["gap"] " "}
       /^FLUSH/ && /switch=true/ && /CLCap.M/ {f++}
       END{printf "%-10s SELECT=%d gap>0=%d stop259&minimal=%d concurrent=%d switchingFLUSH=%d k/gap: %s\n", a, s, g, m, c, f, ks}' $U/$a/cap.csv.trace
  # trough of onDiskSize in the write phase after the first SELECT
  t0=$(awk '/^SELECT/{for(i=1;i<=NF;i++) if($i ~ /^tMs=/){sub("tMs=","",$i); print $i; exit}}' $U/$a/cap.csv.trace)
  awk -F, -v t0=$t0 -v M=$M 'NR>1 && $2=="write" && $1>=t0 {if(mn==""||$3<mn)mn=$3} END{printf "           trough after first SELECT (write phase) = %.0f MiB\n", mn/M}' $U/$a/cap.csv
done
echo "== cluster: du peak and last sample <= TS (apparent size minus 4096), CLD lines in system.log, deletions in debug.log"
for a in 8192 128 256 512; do
  eval $(cat $C/$a/times.txt | tr ' ' '\n' | grep -E '^(T0|T1|TS)=')
  awk -F, -v T0=$T0 -v TS=$TS -v a=$a -v M=$M '$1>=T0 && $1<=TS {v=$2-4096; if(v>pk){pk=v}; last=v}
       END{printf "%-5s du peak=%.0fMiB settled=%.0fMiB ", a, pk/M, last/M}' $C/$a/du.csv
  echo "CLD(lifetime)=$(grep -c 'keyspace1.standard1, Reason: COMMITLOG_DIRTY' $C/$a/system.log) ML=$(grep -c 'keyspace1.standard1, Reason: MEMTABLE_LIMIT' $C/$a/system.log) deletions(lifetime)=$(zcat $C/$a/debug.log.gz | grep -c 'is no longer active and will be deleted') partitions=$(grep -m1 'Total partitions' $C/$a/stress.out | awk '{print $4}') errors=$(grep -m1 'Total errors' $C/$a/stress.out | awk '{print $4}') config=$(grep -o 'commitlog_total_space=[^;]*' $C/$a/system.log | head -1)"
done
