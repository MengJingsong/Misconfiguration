#!/usr/bin/env bash
# Run a queue of U12 runs sequentially (one measured node at a time). Launch detached:
#   ( setsid nohup bash /mydata/s4/u12/h/queue.sh <queue-file> < /dev/null > /dev/null 2>&1 & )
# Queue line: <arm> <run> <golden|N> <base|patched> <heap> <direct> [VERIFY=1] [KEEPDUMP=1] [-- extra JVM opts]
# No run starts after 13:15 EST (checked before each line). After each run: heap dump (if any) -> hprof_direct.py ->
# <run>/direct-holders.txt; the dump is deleted unless KEEPDUMP=1 (then gzip'd).
U=/mydata/s4/u12; H=$U/h; Q=$1
log(){ echo "[$(TZ=America/New_York date '+%F %T')] $*" >> $U/runs/queue.log; }
log "queue $Q start"
while read -r line; do
  [ -z "$line" ] && continue; case "$line" in \#*) continue ;; esac
  now=$(TZ=America/New_York date +%H%M); if [ "$now" -ge 1315 ]; then log "STOP: 13:15 EST reached, skipping: $line"; continue; fi
  [ -f $U/runs/STOP ] && { log "STOP file, skipping: $line"; continue; }
  pre=${line%% -- *}; extra=""; [[ "$line" == *" -- "* ]] && extra=${line#* -- }
  set -- $pre; arm=$1; run=$2; g=$3; b=$4; hp=$5; dm=$6; shift 6; V=0; K=0
  for o in "$@"; do case $o in VERIFY=1) V=1 ;; KEEPDUMP=1) K=1 ;; esac; done
  extra=${extra//@RUN@/$U/runs/$run}
  log "start $run ($arm $g $b $hp/$dm V=$V K=$K extra=[$extra])"
  VERIFY=$V bash $H/run.sh $arm $run $g $b $hp $dm $extra < /dev/null
  R=$U/runs/$run; d=$(ls $R/dumps/*.hprof 2>/dev/null | head -1)
  if [ -n "$d" ]; then
    python3 $H/hprof_direct.py $d 6 > $R/direct-holders.txt 2>&1 < /dev/null
    if [ $K = 1 ]; then gzip -1 $d; else rm -f $d; fi
  fi
  log "end $run: $(head -1 $R/outcome.txt | cut -c1-250)"
done < $Q
log "queue $Q end"
