#!/usr/bin/env bash
# U6: wait (bounded, 3 h) for the main series to finish, then run list-2 in the same ssh session.
W=/mydata/s4/u6-w4
for i in $(seq 1 1080); do grep -q "SERIES DONE" $W/runs/series-list-main.txt.log 2>/dev/null && break; sleep 10; done
bash $W/harness/series.sh $W/harness/list-2.txt
