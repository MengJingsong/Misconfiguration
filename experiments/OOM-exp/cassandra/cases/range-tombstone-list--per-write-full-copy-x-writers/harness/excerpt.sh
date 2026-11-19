#!/bin/bash
# U11: copy small excerpts of one run into <case>/logs/<label>/ (full logs stay in /mydata/s4/u11-w4/<label>/).
R=/mydata/s4/u11-w4/$1; H=$(dirname "$(readlink -f "$0")"); O=$H/../logs/$1; mkdir -p "$O"
cp "$R/logs/driver.log" "$R/logs/settings.json" "$R/logs/fill.json" "$R/logs/write.json" "$R/logs/conf.diff" "$O/" 2>/dev/null
[ -f "$R/logs/persec.csv" ] && cp "$R/logs/persec.csv" "$O/"
python3 -I "$H/analyze.py" "$R" > "$O/analysis.json"
head -1 "$R/logs/poll.log" > "$O/poll-every10s.txt"; awk 'NR>1 && NR%10==0' "$R/logs/poll.log" >> "$O/poll-every10s.txt"
grep -E '\[gc *\] GC\(' "$R/logs/gc.log" | grep -E 'Pause' > /tmp/u11-$$.txt
{ echo "# pause lines: total $(wc -l < /tmp/u11-$$.txt); first 5, then every 100th, then last 20 (full: $R/logs/gc.log)"; head -5 /tmp/u11-$$.txt; awk 'NR%100==0' /tmp/u11-$$.txt; tail -20 /tmp/u11-$$.txt; } > "$O/gc-excerpt.txt"
rm -f /tmp/u11-$$.txt
for h in "$R"/hist/*.txt; do head -25 "$h" > "$O/hist-$(basename "$h")"; grep '^Total' "$h" >> "$O/hist-$(basename "$h")"; done
grep -nF -A12 'java.lang.OutOfMemoryError' "$R/logs/system.log" 2>/dev/null | head -60 > "$O/oom-system-log.txt"
grep -nF -B2 -A25 'java.lang.OutOfMemoryError' "$R/logs/stdout.txt" 2>/dev/null | head -120 > "$O/oom-stdout.txt"
find "$O" -size 0 -delete
