#!/usr/bin/env bash
cd /mydata/oom-recheck/R2
until grep -q "run-seq DONE" run-A.log; do sleep 5; done
HINT_LEAD=50 bash run-seq.sh list-B.txt > run-B.log 2>&1
