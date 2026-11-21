#!/bin/bash
# R17: copy small excerpts of one run into <case>/logs/<label>/ (full logs stay in /mydata/s4/r17/<label>/).
R=/mydata/s4/r17/$1; H=$(dirname "$(readlink -f "$0")"); O=$H/../logs/$1; mkdir -p "$O"
for f in driver.log settings.json fill.json hot.json blob.json write.json conf.diff flushes.txt oom-grep.txt poll.err; do [ -f "$R/logs/$f" ] && cp "$R/logs/$f" "$O/"; done
python3 -I "$H/analyze.py" "$R" > "$O/analysis.json"
head -1 "$R/logs/poll.log" > "$O/poll-every10s.txt"; awk 'NR>1 && NR%10==0' "$R/logs/poll.log" >> "$O/poll-every10s.txt"
echo "# last 30 poll rows" >> "$O/poll-every10s.txt"; tail -30 "$R/logs/poll.log" >> "$O/poll-every10s.txt"
for c in hot blob; do [ -f "$R/logs/$c.csv" ] && { head -1 "$R/logs/$c.csv"; awk 'NR>1 && NR%10==0' "$R/logs/$c.csv"; tail -3 "$R/logs/$c.csv"; } > "$O/$c-every10s.csv"; done
grep -hE '\[gc *\] GC\(' "$R"/logs/gc.log* 2>/dev/null | grep -E 'Pause' > /tmp/r17-$$.txt
{ echo "# pause lines: total $(wc -l < /tmp/r17-$$.txt); first 5, every 200th, last 40 (full: $R/logs/gc.log*)"; head -5 /tmp/r17-$$.txt; awk 'NR%200==0' /tmp/r17-$$.txt; tail -40 /tmp/r17-$$.txt; } > "$O/gc-excerpt.txt"
rm -f /tmp/r17-$$.txt
for h in "$R"/hist/*.txt; do [ -f "$h" ] || continue; case "$h" in *hprof*) cp "$h" "$O/";; *) { head -25 "$h"; grep -E 'Mutation |PartitionUpdate |StorageProxy\$' "$h"; grep '^Total' "$h"; } > "$O/hist-$(basename "$h")";; esac; done
grep -nF -B3 -A20 'OutOfMemoryError' "$R/logs/system.log" 2>/dev/null | head -80 > "$O/oom-system-log.txt"
grep -nF -B2 -A60 'OutOfMemoryError' "$R/logs/stdout.txt" 2>/dev/null | head -140 > "$O/oom-stdout.txt"
find "$O" -size 0 -delete
