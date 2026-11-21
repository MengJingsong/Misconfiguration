#!/usr/bin/env bash
# R10 smaps.sh <pid> <csv> [interval s, default 1]: every interval, every anonymous mapping >= 8 MiB of <pid> from
# /proc/<pid>/smaps: epoch_ms,start_addr,size_kb,rss_kb (per-holder U independent of K; design §2.5 phase 0 / §2.6 (a)).
pid=$1; csv=$2; iv=${3:-1}
echo "epoch_ms,start,size_kb,rss_kb" > "$csv"
while kill -0 $pid 2>/dev/null; do
  t=$(date +%s%3N)
  awk -v t=$t '
    function flush() { if (anon && sz >= 8192) printf "%s,%s,%d,%d\n", t, st, sz, rss }
    /^[0-9a-f]+-[0-9a-f]+ / { flush(); split($1, a, "-"); st=a[1]; anon=(NF==5 && $5=="0"); sz=0; rss=0; next }
    /^Size:/ { sz=$2; next }
    /^Rss:/ { rss=$2; next }
    END { flush() }' /proc/$pid/smaps 2>/dev/null >> "$csv"
  sleep $iv
done
