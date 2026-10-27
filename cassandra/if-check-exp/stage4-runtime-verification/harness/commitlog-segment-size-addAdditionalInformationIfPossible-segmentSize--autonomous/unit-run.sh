#!/bin/bash
# Unit tier (B2, amendment D-R1). Usage: bash unit-run.sh <tree> <outdir>
# Mounts a 4 GiB and a 16 MiB tmpfs (sudo), runs SgAddInfoProbeTest once via ant testsome, checks the EXPECTED lines against
# the RESULT file, unmounts. Stops on the first failed check; exit 1 on any mismatch. Nothing it starts survives it.
set -u
TREE=${1:?}; OUT=${2:?}
HERE=$(cd "$(dirname "$0")" && pwd)
BIG=$HOME/s4-b10-sg-big; SMALL=$HOME/s4-b10-sg-small
mkdir -p $OUT; : > $OUT/probe.out
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a $OUT/session.log; }
cleanup() { for m in $BIG $SMALL; do for i in 1 2 3 4 5; do sudo umount $m 2>/dev/null && break; sleep 2; done; done; rmdir $BIG $SMALL 2>/dev/null; log "unmounted; mounts left: [$(findmnt -rn -o TARGET | grep s4-b10-sg | tr '\n' ' ')]"; }
fail() { log "FAIL: $*"; exit 1; }
trap cleanup EXIT
[ "$(git -C $TREE describe --tags)" = cassandra-5.0.9 ] || fail "tree not at cassandra-5.0.9"
findmnt -rn -o TARGET | grep -q s4-b10-sg && fail "a s4-b10-sg mount already exists"
mkdir -p $BIG $SMALL
sudo mount -t tmpfs -o size=4g tmpfs $BIG && sudo mount -t tmpfs -o size=16m tmpfs $SMALL || fail mount
sudo chown $(id -u):$(id -g) $BIG $SMALL
log "df -B1: big=$(df -B1 --output=size,avail $BIG | tail -1) small=$(df -B1 --output=size,avail $SMALL | tail -1)"
[ "$(df -B1 --output=size $SMALL | tail -1 | tr -d ' ')" = 16777216 ] || fail "small tmpfs is not 16 MiB"
cp $HERE/SgAddInfoProbeTest.java $TREE/test/unit/org/apache/cassandra/db/commitlog/ || fail copy
log "+ ant testsome SgAddInfoProbeTest#run"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.SgAddInfoProbeTest -Dtest.methods=run \
    "-Dtest.jvm.args=-Dsgtest.big=$BIG -Dsgtest.small=$SMALL -Dsgtest.out=$OUT/probe.out" </dev/null ) > $OUT/ant.log 2>&1
grep -E 'Tests run|BUILD' $OUT/ant.log | tee -a $OUT/session.log
cp $TREE/build/test/logs/TEST-org.apache.cassandra.db.commitlog.SgAddInfoProbeTest*.xml $OUT/ 2>/dev/null
RC=0
exp() { grep -qF "$1" $OUT/probe.out && log "EXPECTED ok: $1" || { log "EXPECTED MISSING: $1"; RC=1; }; }
F=$(grep -c '^RESULT FAIL' $OUT/probe.out); D=$(grep -c '^RESULT DONE failures=0' $OUT/probe.out)
log "RESULT lines: PASS=$(grep -c '^RESULT PASS' $OUT/probe.out) FAIL=$F DONE(failures=0)=$D"
exp 'RESULT PASS KA small volume total'
exp 'RESULT PASS KA big volume full'
exp 'RESULT PASS KA small volume full'
exp 'RESULT PASS S1 small empty seg32 seg=32MiB aug=true only=16777216'
exp 'RESULT PASS S2 big empty seg32 seg=32MiB aug=false'
for s in 8 32 1024 2047; do exp "RESULT PASS S3 big empty seg$s "; exp "RESULT PASS S4 big FULL seg$s seg=${s}MiB aug=false"; done
exp 'RESULT PASS S5 small FULL seg32 seg=32MiB aug=true only=16777216'
exp 'RESULT PASS S6 small FULL seg8 seg=8MiB aug=false'
exp 'RESULT PASS S6 small FULL seg16 seg=16MiB aug=false'
exp 'RESULT PASS S6 small FULL seg17 seg=17MiB aug=true only=16777216'
exp 'RESULT PASS S7 nonexistent under big'
exp 'RESULT PASS S7 nonexistent under small seg=32MiB aug=true only=16777216'
exp 'RESULT PASS S8 handleCommitError stop_commit small'
exp 'RESULT PASS S8 handleCommitError ignore big'
for s in 8 32 64; do exp "RESULT PASS C1 segment file length seg$s"; done
[ $F = 0 ] && [ $D = 1 ] || RC=1
log "unit-run end rc=$RC"
exit $RC
