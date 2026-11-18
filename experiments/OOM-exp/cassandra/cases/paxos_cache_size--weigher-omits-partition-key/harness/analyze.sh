#!/usr/bin/env bash
# analyze.sh <run-id> [key-length=61440]: dump analyses for a B12 OOM run (OOM thread, bigarrays >= len, retainers of byte[len]).
W=/mydata/s4/b12-w2; R=$W/runs/$1; L=${2:-61440}; f=$(ls /dev/shm/b12-w2/$1/*.hprof)
python3 -I $W/harness/hprof_oome_thread.py $f 14 > $R/oome-thread.txt 2>&1
{ echo "== $1 $f $(date +%FT%T)"; /usr/bin/time -f "bigarrays %e s %M KB" python3 -I $W/harness/bigarrays.py $f $L; } > $R/bigarrays.txt 2>&1
{ /usr/bin/time -f "retainers %e s %M KB" python3 -I $W/harness/retainers.py $f byte $L 8; } > $R/retainers.txt 2>&1
echo done >> $R/retainers.txt
