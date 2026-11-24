#!/bin/bash
# R22 3-b confirm (pc72, 2026-11-23), from stage 2's excerpt.sh: copy small excerpts of one run into <out>/<label>/
# (full logs stay in /mydata/s4/3b-R22/<label>/ on pc72). usage: excerpt.sh <label> <out dir> [oom_at_W_s]
R=/mydata/s4/3b-R22/$1; H=$(dirname "$(readlink -f "$0")"); O=$2/$1; mkdir -p "$O"
for f in driver.log setup.json settings.json fill.json hot.json blob0.json blob1.json blob2.json victim.json victim.err conf.diff flushes.txt oom-grep.txt poll.err vmflags.txt preauth.txt authcheck.json authcheck-syslog.txt; do [ -f "$R/logs/$f" ] && cp "$R/logs/$f" "$O/"; done
python3 -I "$H/analyze.py" "$R" > "$O/analysis.json" 2>/dev/null
[ -f "$R/logs/victim.csv" ] && { python3 -I "$H/vsum.py" "$R" ${3:-} > "$O/vsum.txt"; cp "$R/logs/victim.csv" "$O/victim.csv"; }
head -1 "$R/logs/poll.log" > "$O/poll-every10s.txt"; awk 'NR>1 && NR%10==0' "$R/logs/poll.log" >> "$O/poll-every10s.txt"
echo "# last 30 poll rows" >> "$O/poll-every10s.txt"; tail -30 "$R/logs/poll.log" >> "$O/poll-every10s.txt"
for c in hot blob0 blob1 blob2; do [ -f "$R/logs/$c.csv" ] && { head -1 "$R/logs/$c.csv"; awk 'NR>1 && NR%10==0' "$R/logs/$c.csv"; tail -3 "$R/logs/$c.csv"; } > "$O/$c-every10s.csv"; done
grep -hE '\[gc *\] GC\(' "$R"/logs/gc.log* 2>/dev/null | grep -E 'Pause' > $O/.pauses.tmp
{ echo "# pause lines: total $(wc -l < $O/.pauses.tmp); first 5, every 200th, last 40 (full: $R/logs/gc.log*)"; head -5 $O/.pauses.tmp; awk 'NR%200==0' $O/.pauses.tmp; tail -40 $O/.pauses.tmp; } > "$O/gc-excerpt.txt"
grep -h 'Humongous regions' "$R"/logs/gc.log* 2>/dev/null | tail -20 > "$O/gc-humongous-last20.txt"
rm -f $O/.pauses.tmp
for h in "$R"/hist/*.txt; do [ -f "$h" ] || continue; case "$h" in *hprof*) cp "$h" "$O/";; *) { head -25 "$h"; grep -E 'Mutation |PartitionUpdate |StorageProxy\$' "$h"; grep '^Total' "$h"; } > "$O/hist-$(basename "$h")";; esac; done
grep -nF -B3 -A40 'java.lang.OutOfMemoryError' "$R/logs/system.log" 2>/dev/null | head -120 > "$O/oom-system-log.txt"
grep -nF -B2 -A60 'java.lang.OutOfMemoryError' "$R/logs/stdout.txt" 2>/dev/null | head -140 > "$O/oom-stdout.txt"
grep -hE 'WARN|ERROR' "$R/logs/system.log" 2>/dev/null | grep -v 'JVM Arguments' | cut -c1-400 | awk '{k=$0; sub(/[0-9T:,-]+ /,"",k)} 1' | head -200 > "$O/system-warn-error-head200.txt"
find "$O" -size 0 -delete
