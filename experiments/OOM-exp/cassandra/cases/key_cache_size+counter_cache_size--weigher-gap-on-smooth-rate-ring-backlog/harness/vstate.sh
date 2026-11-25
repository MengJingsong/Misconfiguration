#!/usr/bin/env bash
# R25 (copied from R19, paths /mydata/r25, R1 on ms0640; 2026-11-24). R19 (R11 vstate.sh, paths only), runs on V: one-line state for arm.sh's observation loop.
#   vstate.sh <gate.log>  ->  "DEAD" | "ALIVE last=<pending> max30=<max pending over the last 30 s> n30=<readings in 30 s>"
P=$(cat /mydata/r25/inst/V/cass.pid 2>/dev/null)
kill -0 "$P" 2>/dev/null || { echo DEAD; exit 0; }
now=$(date +%s%3N)
tail -400 "$1" | awk -v now=$now '$2 ~ /^pending=/ { split($2,a,"="); last=a[2]; if ($1 >= now-30000) { n++; if (a[2]>m) m=a[2] } }
  END { printf "ALIVE last=%s max30=%d n30=%d\n", (last==""?"-":last), m, n }'
