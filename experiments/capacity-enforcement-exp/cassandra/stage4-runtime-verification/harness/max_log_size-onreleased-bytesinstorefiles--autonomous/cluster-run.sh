#!/usr/bin/env bash
# o72 cluster tier (B3e with amendments M5-M8, D1, M9). Runs on the node as a non-root user,
# detached (nohup setsid); its PID goes to /mydata/s4/DRIVER-jingsong-o72.pid.
# Usage: cluster-run.sh [tags...]   (default: C1 K1 K2 C2)
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
BASE=/mydata/jingsong-cass-s4/o72
RUN=$BASE/cluster
mkdir -p $RUN/logs $RUN/results
exec > >(tee -a $RUN/results/cluster-driver.log) 2>&1
set -x
TAGS=${*:-C1 K1 K2 C2}
date; date +%s%3N; hostname; uname -m
fail() { echo "FAIL: $*"; date; exit 1; }
SAMPLER_PID=
stop_sampler() { if [ -n "$SAMPLER_PID" ]; then kill $SAMPLER_PID 2>/dev/null; wait $SAMPLER_PID 2>/dev/null; fi; SAMPLER_PID=; }  # fixed after run 1: an empty PID made `wait` hang on the tee at exit
trap 'stop_sampler' EXIT

if [ ! -d $RUN/src ]; then
  cp -a $BASE/build-copy $RUN/src || fail "copy"
  python3 $HERE/cluster-setup.py $RUN || fail "yaml"
fi
cd $RUN/src
grep -n "^data_file_directories\|^    - $RUN\|^commitlog_directory\|^hints_directory\|^saved_caches_directory\|^cdc_raw_directory\|^auto_snapshot\|^full_query_logging_options\|^  log_dir\|^  allow_nodetool" conf/cassandra.yaml
export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_LOG_DIR=$RUN/logs
NT() { bin/nodetool "$@"; }

if ! pgrep -u $(id -u) -f CassandraDaemon >/dev/null; then
  for p in 7000 7199 9042; do ss -ltn "sport = :$p" | grep -q LISTEN && fail "port $p busy"; done
  ulimit -n 100000
  bin/cassandra -p $RUN/cassandra.pid > $RUN/logs/start.out 2>&1
  for i in $(seq 1 90); do
    sleep 2
    pgrep -u $(id -u) -f CassandraDaemon >/dev/null || fail "daemon died at start"
    NT status 2>/dev/null | grep -q '^UN' && NT statusbinary 2>/dev/null | grep -q running && break
  done
  NT status | grep '^UN' || fail "node not UN"
  NT statusbinary
fi
NT setlogginglevel org.apache.cassandra.utils.binlog.DeletingArchiver DEBUG
NT getlogginglevels | grep -i binlog

M_K1=314572800; M_K2=692060160; M_C1=17179869184
[ -f $RUN/results/scale.txt ] && . $RUN/results/scale.txt

for tag in $TAGS; do
  echo "===== RUN $tag start $(date) $(date +%s%3N)"
  avail=$(df -B1 --output=avail $RUN | tail -1)
  df -h $RUN
  [ "$avail" -ge $((15*1024*1024*1024)) ] || fail "less than 15 GiB free before $tag"
  case $tag in
    C1) M=$M_C1; EXTRA=() ;;
    K1) M=$M_K1; EXTRA=() ;;
    K2) M=$M_K2; EXTRA=() ;;
    C2) M=$M_K1; EXTRA=(--archive-command "/bin/true %path") ;;
  esac
  F=$RUN/fql-$tag
  mkdir -p $F
  ( while sleep 5; do L=$(ls $F/*.cq4 2>/dev/null | sort); n=$(echo "$L" | grep -c cq4); r=$(echo "$L" | head -n -1 | xargs -r stat -c %s | awk '{s+=$1}END{print s+0}'); t=$(echo "$L" | xargs -r stat -c %s | awk '{s+=$1}END{print s+0}'); a=$(du -B1 -s $F | cut -f1); echo "$(date +%s) $n $r $t $a"; done > $RUN/results/sample-$tag.txt ) &
  SAMPLER_PID=$!
  NT enablefullquerylog --path $F --roll-cycle MINUTELY --blocking true --max-log-size $M "${EXTRA[@]}" || fail "enable $tag"
  NT getfullquerylog > $RUN/results/conf-$tag.txt 2>&1; cat $RUN/results/conf-$tag.txt
  echo "stress start $tag $(date +%s%3N)"
  tools/bin/cassandra-stress write n=480000 cl=ONE -col 'size=FIXED(1000)' 'n=FIXED(5)' -rate threads=16 'fixed=400/s' -node 127.0.0.1 -log file=$RUN/results/stress-$tag.log > $RUN/logs/stress-$tag.out 2>&1
  echo "stress rc=$? end $tag $(date +%s%3N)"
  sed -n '/^Results:/,$p' $RUN/logs/stress-$tag.out | head -30
  sleep 70
  tools/bin/cassandra-stress write n=1 -rate threads=1 -node 127.0.0.1 > $RUN/logs/stress1-$tag.out 2>&1; echo "single write rc=$?"
  sleep 10
  NT disablefullquerylog
  sleep 6; stop_sampler
  ls -l $F > $RUN/results/ls-$tag.txt
  cp $RUN/logs/system.log $RUN/results/system-$tag.log
  cp $RUN/logs/debug.log $RUN/results/debug-$tag.log
  grep -h "rolled file size\|Deleted chronicle store file\|Failed to delete chronicle" $RUN/logs/debug.log | grep "fql-$tag/" > $RUN/results/archiver-$tag.txt
  echo "deletions $tag: $(grep -c 'Deleted chronicle store file' $RUN/results/archiver-$tag.txt) releases: $(grep -c 'rolled file size' $RUN/results/archiver-$tag.txt)"
  bin/cqlsh -e "TRUNCATE keyspace1.standard1" 127.0.0.1 || echo "truncate failed"
  [ $tag = K1 ] || rm -rf $F
  if [ $tag = C1 ]; then
    FP=$(grep 'rolled file size' $RUN/results/archiver-C1.txt | sed 's/.*rolled file size \([0-9]*\).*/\1/' | sort -n | awk '{a[NR]=$1} END{ if(NR%2) print a[(NR+1)/2]; else print int((a[NR/2]+a[NR/2+1])/2) }')
    echo "C1 F'=$FP"
    if [ -n "$FP" ] && python3 -c "import sys; f=$FP; sys.exit(0 if abs(f-125829120)/125829120 > 0.25 else 1)"; then
      echo "M_K1=$(python3 -c "print(int(2.5*$FP))"); M_K2=$(python3 -c "print(int(5.5*$FP))")" > $RUN/results/scale.txt
    else
      echo "M_K1=314572800; M_K2=692060160" > $RUN/results/scale.txt
    fi
    echo "FPRIME_C1=$FP" >> $RUN/results/scale.txt
    cat $RUN/results/scale.txt; . $RUN/results/scale.txt
  fi
  echo "===== RUN $tag end $(date) $(date +%s%3N)"
done
echo CLUSTER-RUNS-DONE; date
