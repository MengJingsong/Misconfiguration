#!/usr/bin/env bash
# B26 VERIFY+PROBE lifetime (heap 8G, from the template; not a reading). Steps (a)-(d) of the frozen design.
#   nodetool client heap for (c): shipped 128m first; if that nodetool OOMs on the returned 16/30 MB strings, rerun (c)
#   with MAX_HEAP_SIZE=1g for nodetool only (client tool; recorded).
set -uo pipefail
ROOT=/mydata/s4/b26; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NTB="$ROOT/tree/bin/nodetool -h 127.0.0.1"
L=VERIFY; R=$ROOT/runs/$L; CL="bash $H/client.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V start $L A 8G || exit 1; $V ready $L || exit 1
log "(a)"; $CL v-a1 one 127.0.0.1 S16 t1; $CL v-a2 one 127.0.0.1 S30 t1
log "(b)"; $NTB profileload b26 t1 5000 -s 2000 2>&1 | head -3
for SH in S16 S30; do
  for NH in default 1g; do
    log "(c) $SH nodetool heap $NH"
    ( if [ $NH != default ]; then export MAX_HEAP_SIZE=$NH; fi; $NTB profileload b26 t1 5000 -a LOCAL_READ_TIME -k 1 > $R/render-$SH-$NH.out 2> $R/render-$SH-$NH.err ) &
    NP=$!; sleep 1.5; $CL v-c one 127.0.0.1 $SH t1; wait $NP; echo "nodetool exit $?"
    echo "bytes=$(wc -c < $R/render-$SH-$NH.out)"; awk '{print length($0) "\t" substr($0,1,200)}' $R/render-$SH-$NH.out | head -12; tail -3 $R/render-$SH-$NH.err | cut -c1-200
    grep -q 'ck IN' $R/render-$SH-$NH.out && break
  done
done
log "(d) probe"
$CL p1 run 127.0.0.1 S16 t1 1 10 | grep SUMMARY
$CL p2 run 127.0.0.1 S16 t1 4 30 | grep SUMMARY
$CL p3 run 127.0.0.1 S30 t1 4 30 | grep SUMMARY
$CL p4 run 127.0.0.1 S30 t1 8 30 | grep SUMMARY
log "(d) S16 c=4 with sampling (LOCAL_READ_TIME, 20 s)"
( $NTB profileload b26 t1 20000 -a LOCAL_READ_TIME -k 1 > $R/probe-sampling.out 2> $R/probe-sampling.err ) &
NP=$!; $CL p5 run 127.0.0.1 S16 t1 4 30 > $R/p5.out; grep SUMMARY $R/p5.out; grep '^S ' $R/p5.out | cut -c1-120 | head -30; wait $NP; echo "nodetool exit $? bytes=$(wc -c < $R/probe-sampling.out)"
$V read $L probe-end
echo "slow-op lines: $(grep -c 'operations were slower than' $R/logs/debug.log)  cancelled: $(grep -c 'Query cancelled' $R/logs/debug.log)"
$V stop $L
echo VERIFY done
