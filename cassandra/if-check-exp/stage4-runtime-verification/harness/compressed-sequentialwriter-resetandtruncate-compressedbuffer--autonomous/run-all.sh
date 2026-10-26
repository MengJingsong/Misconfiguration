#!/usr/bin/env bash
# Run 1 of the cluster tier: each arm is its own node lifetime, one at a time. Usage on the node:  bash run-all.sh
set -u
ulimit -n 100000
export CS_RUN=${CS_RUN:-run1}
H=$HOME/s4-cs-harness
for a in C4 C16 C256 C1024 W4 U; do python3 -I $H/cluster-run.py $a > $HOME/s4-cs-logs/$CS_RUN-$a.out 2>&1; echo "$a rc=$? $(date -u +%FT%TZ)" >> $HOME/s4-cs-logs/$CS_RUN-all.log; done
for f in 0.55 0.40 0.70; do python3 -I $H/cluster-run.py S1 $f > $HOME/s4-cs-logs/$CS_RUN-S1-$f.out 2>&1; echo "S1 $f rc=$? $(date -u +%FT%TZ)" >> $HOME/s4-cs-logs/$CS_RUN-all.log; done
for f in 0.55; do python3 -I $H/cluster-run.py S2 $f > $HOME/s4-cs-logs/$CS_RUN-S2-$f.out 2>&1; echo "S2 $f rc=$? $(date -u +%FT%TZ)" >> $HOME/s4-cs-logs/$CS_RUN-all.log; done
echo ALLDONE >> $HOME/s4-cs-logs/$CS_RUN-all.log
