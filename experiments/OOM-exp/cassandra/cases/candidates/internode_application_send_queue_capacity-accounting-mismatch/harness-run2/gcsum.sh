#!/usr/bin/env bash
# Summarise a JVM's G1 log around a stall: Full GC count, worst post-GC occupancy, OOM marker,
# and whether Full GCs were still running in the last 30 s of the log (no recovery).
#   gcsum.sh <dir-with-gc.log*> <heap_MiB>
D=$1; H=$2
cat "$D"/gc.log* | grep -E "Pause Full|ReportJavaOutOfMemory|Pause Young" | sort -s -k1,1 | awk -v H="$H" '
  /Pause Full/ { n++; match($0,/[0-9]+M->[0-9]+M/); s=substr($0,RSTART,RLENGTH); split(s,a,"->"); after=a[2]+0;
                 if (after>mx) mx=after; if (after>0.95*H && !first) first=substr($1,2,23); last=substr($1,2,23) }
  /ReportJavaOutOfMemory/ { oom++ }
  { t=substr($1,2,23) }
  END { printf "full_gcs=%d max_after_full=%dMiB (%.1f%% of heap) first_full_gt95=%s last_full=%s log_end=%s ReportJavaOutOfMemory=%d\n", n, mx, 100*mx/H, first, last, t, oom }'
