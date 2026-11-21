#!/usr/bin/env bash
# R18 phase 1: Q7a..Q7d in parallel (keys [56M,63M) [63M,70M) [70M,77M) [77M,84M)), then checks; chmod a-w.
G=/mydata/s4/r18/gen; L=/mydata/s4/r18/logs
echo "$(date +%s%3N) genall start" >> $L/gen-times.txt
bash $G/gen.sh Q7a 56000000 63000000 & bash $G/gen.sh Q7b 63000000 70000000 & bash $G/gen.sh Q7c 70000000 77000000 & bash $G/gen.sh Q7d 77000000 84000000 &
wait
echo "$(date +%s%3N) genall end" >> $L/gen-times.txt
for s in Q7a Q7b Q7c Q7d; do grep -hE ' start | done ' $L/gen-$s.log | sed "s/^/$s /" >> $L/gen-times.txt; done
bash $G/checkdata.sh > $L/checkdata-q7.csv 2>&1
chmod a-w /mydata/s4/r18/data/pristine/Q7*/*
ls -l /mydata/s4/r18/data/pristine/Q7*/ > $L/q7-listing.txt
echo "$(date +%s%3N) GENALL DONE" >> $L/gen-times.txt
