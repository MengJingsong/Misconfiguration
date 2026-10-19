#!/usr/bin/env bash
# Emulates a CDC consumer for the cdc_total_space case (case §9e, release step and consumer control).
#
#   cdc-consumer.sh <cdc_raw directory> once            one pass, then exit
#   cdc-consumer.sh <cdc_raw directory> loop <seconds>  a pass every <seconds> until killed
#
# A pass deletes the link and the index file of every segment whose index file's second line is COMPLETED,
# which is what a consumer does when it has finished reading a segment (CommitLogSegment.writeCDCIndexFile,
# CommitLogSegment.java:379-392). It never touches a segment that is still being written (no COMPLETED line),
# and never a link without an index file. One line per deletion on stdout: ms,deleted,<link name>; one summary
# line per pass: ms,pass,<number deleted>.
set -u
dir=${1:?usage: cdc-consumer.sh <cdc_raw directory> once|loop <seconds>}
mode=${2:-once}
every=${3:-1}

pass() {
  local n=0 idx link
  for idx in "$dir"/CommitLog-*_cdc.idx; do
    [ -e "$idx" ] || continue
    if [ "$(sed -n 2p "$idx" 2> /dev/null)" = COMPLETED ]; then
      link=${idx%_cdc.idx}.log
      rm -f -- "$link" "$idx" && { echo "$(date +%s%3N),deleted,$(basename "$link")"; n=$((n + 1)); }
    fi
  done
  echo "$(date +%s%3N),pass,$n"
}

case $mode in
  once) pass ;;
  loop) while :; do pass; sleep "$every"; done ;;
  *)    echo "usage: cdc-consumer.sh <cdc_raw directory> once|loop <seconds>" >&2; exit 2 ;;
esac
