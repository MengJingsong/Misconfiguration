#!/usr/bin/env bash
# Non-intrusive heap summary from a G1 unified GC log (B6 run 3).
#   gcpeak.sh <dir-with-gc.log*> <heap_MiB>
# Prints: GC pause count, peak occupancy after ANY pause (upper bound on live heap), Full GC count,
# peak after Full GC, OOM marker, and the service-loss check of the protocol (default criterion):
# window from the first to the end of the last Full GC leaving > 95% of heap, Full-GC pause time in it,
# and whether pause/window >= 90% over a window >= 60 s.
D=$1; H=$2
cat "$D"/gc.log* 2>/dev/null | grep -E "Pause (Full|Young|Remark|Cleanup)|ReportJavaOutOfMemory" | sort -s -k1,1 | awk -v H="$H" '
  /ReportJavaOutOfMemory/ { oom++; next }
  {
    if (!match($0,/[0-9]+M->[0-9]+M/)) next
    split(substr($0,RSTART,RLENGTH),a,"->"); after=a[2]+0
    match($0,/\]\[[0-9.]+s\]/); up=substr($0,RSTART+2,RLENGTH-4)+0
    match($0,/[0-9.]+ms$/); ms=substr($0,RSTART,RLENGTH-2)+0
    n++; if (after>mxa) mxa=after
    if ($0 ~ /Pause Full/) {
      nf++; if (after>mxf) mxf=after
      if (after>0.95*H) { if (!w0) w0=up; w1=up+ms/1000; pf+=ms/1000; nhf++ }
    }
  }
  END {
    win=(w0? w1-w0 : 0); ratio=(win>0? pf/win : 0)
    sl=(win>=60 && ratio>=0.9) ? "MET" : "not met"
    printf "pauses=%d max_after_any=%dMiB(%.1f%%) full_gcs=%d max_after_full=%dMiB(%.1f%%) ReportJavaOutOfMemory=%d | full>95%%: n=%d window=%.0fs pause=%.0fs (%.0f%%) service_loss=%s\n",
      n, mxa, 100*mxa/H, nf, mxf, 100*mxf/H, oom, nhf, win, pf, 100*ratio, sl }'
