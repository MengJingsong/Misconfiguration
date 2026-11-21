#!/usr/bin/env bash
# R11, runs on V: one-line state for arm.sh's observation loop.
#   vstate.sh <gate.log>  ->  "DEAD" | "ALIVE last=<pending> max30=<max pending over the last 30 s> n30=<readings in 30 s>"
P=$(cat /mydata/r11/inst/V/cass.pid 2>/dev/null)
kill -0 "$P" 2>/dev/null || { echo DEAD; exit 0; }
now=$(date +%s%3N)
tail -400 "$1" | awk -v now=$now '$2 ~ /^pending=/ { split($2,a,"="); last=a[2]; if ($1 >= now-30000) { n++; if (a[2]>m) m=a[2] } }
  END { printf "ALIVE last=%s max30=%d n30=%d\n", (last==""?"-":last), m, n }'
