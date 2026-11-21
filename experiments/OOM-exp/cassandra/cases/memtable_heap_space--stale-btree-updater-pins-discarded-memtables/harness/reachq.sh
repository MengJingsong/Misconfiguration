#!/usr/bin/env bash
# R21 dump-analysis queue (design §2.5): for each dump in /mydata/s4/r21/dumps/ in order (file name <label>--<tag>.hprof), run
# hprof_scan.py, hprof_reach.py (and hprof_refs.py discarded, depth 4, where <dump>.refs exists) under nice -n 19 taskset -c 36-39,
# write the JSONs to /mydata/s4/r21/logs/<label>/{scan,reach,refs-disc}-<tag>.json and the timing to reachq-<tag>.txt, then delete
# the dump. Up to 3 dumps at once (4 cores). Exits when /mydata/s4/r21/reachq.stop exists and no dump is left.
# usage: ( setsid nohup bash reachq.sh < /dev/null > /mydata/s4/r21/logs/reachq.out 2>&1 & )
W=/mydata/s4/r21; H=$W/harness; MAXJ=3
one() {
  f=$1; b=$(basename "$f" .hprof); label=${b%%--*}; tag=${b##*--}; o=$W/logs/$label; mkdir -p "$o"
  t0=$(date +%s)
  nice -n 19 taskset -c 36-39 python3 -I $H/hprof_scan.py "$f" > "$o/scan-$tag.json" 2> "$o/scan-$tag.err"
  t1=$(date +%s)
  nice -n 19 taskset -c 36-39 python3 -I $H/hprof_reach.py "$f" > "$o/reach-$tag.json" 2> "$o/reach-$tag.err"
  t2=$(date +%s)
  if [ -e "$f.refs" ]; then
    nice -n 19 taskset -c 36-39 python3 -I $H/hprof_refs.py "$f" 4 discarded > "$o/refs-disc-$tag.json" 2> "$o/refs-$tag.err"
  fi
  t3=$(date +%s)
  echo "dump=$f bytes=$(stat -c %s "$f") scan_s=$((t1-t0)) reach_s=$((t2-t1)) refs_s=$((t3-t2)) done=$t3" > "$o/reachq-$tag.txt"
  rm -f "$f" "$f.refs" "$f.taken"
  echo "$(date +%s) done $b scan=$((t1-t0))s reach=$((t2-t1))s refs=$((t3-t2))s"
}
echo "$(date +%s) reachq start pid $$"
while :; do
  for f in $(ls -tr $W/dumps/*.hprof 2>/dev/null); do
    [ -e "$f.taken" ] && continue
    [ "$(jobs -rp | wc -l)" -ge $MAXJ ] && break
    touch "$f.taken"
    echo "$(date +%s) take $(basename $f)"
    one "$f" &
  done
  if [ -e $W/reachq.stop ] && [ -z "$(ls $W/dumps/*.hprof 2>/dev/null)" ] && [ "$(jobs -rp | wc -l)" -eq 0 ]; then
    echo "$(date +%s) reachq exit"; exit 0
  fi
  sleep 5
done
