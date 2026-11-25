#!/usr/bin/env bash
# U16 monitors (identical in every arm; from R12's). Usage: monitor.sh <pid> <run dir> <tree>
# every 2 s: GC.heap_info, RssAnon, scope memory.current, /proc/<pid>/io wchar+write_bytes, debug.log* bytes and archive
#            count, /mydata free (disk guard: < 60 GiB -> kill -9, DISKGUARD file);
# every 2 s: Thread.print -> threadcount.py (R_Q, queue-full blocking, worker / drain phase);
# every 10 s: RequestsSize / PausedConnections (sjk mx), tpstats ReadStage + READ dropped, top 10 threads.
PID=$1; R=$2; T=$3; H=$(dirname "$0")
CG=/sys/fs/cgroup$(cut -d: -f3 /proc/$PID/cgroup)
echo "cgroup $CG" > $R/mon-meta.txt
( while kill -0 $PID 2>/dev/null; do
    ts=$(date +%s.%N | cut -c1-14)
    av=$(df -B1 --output=avail /mydata | tail -1 | tr -dc 0-9)
    if [ "$av" -lt 64424509440 ]; then echo "$ts avail=$av" > $R/DISKGUARD; kill -9 $PID; break; fi
    dl=$(stat -c %s $T/logs/debug.log* 2>/dev/null | awk '{s+=$1} END{print s+0}')
    nz=$(ls $T/logs/ 2>/dev/null | grep -c '^debug.log.*zip$')
    io=$(awk '/^wchar|^write_bytes/{printf "%s=%s ", $1, $2}' /proc/$PID/io 2>/dev/null | tr -d ':')
    hi=$(timeout 10 jcmd $PID GC.heap_info 2>/dev/null | tr '\n' '|')
    rss=$(awk '/RssAnon/{print $2}' /proc/$PID/status 2>/dev/null)
    mc=$(cat $CG/memory.current 2>/dev/null)
    echo "$ts rssanon_kb=$rss memcur=$mc debuglog=$dl zips=$nz $io avail=$av $hi" >> $R/heapinfo.txt
    sleep 2
  done ) &
( while kill -0 $PID 2>/dev/null; do
    ts=$(date +%s.%N | cut -c1-14)
    l=$(timeout 15 jcmd $PID Thread.print 2>/dev/null | python3 -I $H/threadcount.py)
    echo "$ts $l" >> $R/threads.txt
    sleep 2
  done ) &
( while kill -0 $PID 2>/dev/null; do
    ts=$(date +%s.%N | cut -c1-14)
    rs=$(timeout 20 $T/bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=Client,name=RequestsSize -f Value --get 2>/dev/null | tail -1)
    pc=$(timeout 20 $T/bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=Client,name=PausedConnections -f Value --get 2>/dev/null | tail -1)
    tp=$(timeout 20 $T/bin/nodetool tpstats 2>/dev/null | awk '$1=="ReadStage"{printf "rs_active=%s rs_pending=%s rs_done=%s ", $2, $3, $4} $1=="READ"||$1=="READ_REQ"{printf "%s_dropped=%s ", $1, $2}')
    echo "$ts requestssize=$rs paused=$pc $tp" >> $R/ksrv.txt
    top -b -H -n 1 -p $PID 2>/dev/null | sed -n '8,17p' | awk -v t=$ts '{print t, $9, $12, $13}' >> $R/top.txt
    sleep 10
  done ) &
wait
