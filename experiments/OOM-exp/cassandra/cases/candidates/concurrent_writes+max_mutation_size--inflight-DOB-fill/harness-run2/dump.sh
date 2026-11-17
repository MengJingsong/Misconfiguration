#!/usr/bin/env bash
# Attribute the victim's heap dump of an arm (pc96): copy the .hprof from V to pc96 local disk, run hprof_direct.py
# (6 hops), store direct-holders.txt in V's run dir and the pc96 mirror, delete the pc96 copy.
#   dump.sh <arm> [keep-on-V 1|0]
A=$1; KEEP=${2:-1}; H=$(cd "$(dirname "$0")" && pwd); R=/mydata/u1r2/runs/$A; M=/mydata/u1r2/mirror/$A; T=/mydata/u1r2/dumps
mkdir -p $T
f=$(ssh ms0625 "ls $R/*.hprof 2>/dev/null | head -1" < /dev/null); [ -z "$f" ] && { echo "no dump for $A"; exit 1; }
ssh ms0625 "cat $f" < /dev/null > $T/$A.hprof
python3 $H/hprof_direct.py $T/$A.hprof 6 > $M/direct-holders.txt 2>&1
ssh ms0625 "cat > $R/direct-holders.txt" < $M/direct-holders.txt
rm -f $T/$A.hprof
[ "$KEEP" = 0 ] && ssh ms0625 "rm -f $f" < /dev/null
tail -30 $M/direct-holders.txt
