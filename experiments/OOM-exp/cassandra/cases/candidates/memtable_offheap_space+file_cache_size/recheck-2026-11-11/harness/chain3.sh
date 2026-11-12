#!/usr/bin/env bash
R=/mydata/oom-recheck/R1
until grep -q "LIST DONE" $R/run2.log; do sleep 10; done
[ -e $R/STOP ] && exit 0
cp $R/oom-run.sh $R/oom-run.v2.sh; cp $R/oom-run.next2.sh $R/oom-run.sh
echo "converge-noinst 3500 1200 1200 preload,cachefill,memburst" > $R/list3.txt
NMT=off POLL_MS=0 bash $R/run-all.sh $R/list3.txt
