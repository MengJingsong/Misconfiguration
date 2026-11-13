#!/usr/bin/env bash
# Amendment 5: run arm.sh in the background; heap-dump the victim at idle and when K first exceeds 440 MiB.
#   netty-probe.sh <name> <N> <rate> <direct>
H=$(cd "$(dirname "$0")" && pwd); NAME=$1; R=/mydata/c1r4/runs/$NAME
DEFAULTS=1 "$H/arm.sh" "$NAME" "$2" "$3" "$4" none 90 > /mydata/c1r4/runs/$NAME.armlog 2>&1 &
AP=$!
until grep -q "load start" "$R/args.txt" 2>/dev/null; do sleep 0.5; kill -0 $AP 2>/dev/null || exit 1; done
VP=$("$H/ctl.sh" pid V)
# idle dump was taken too late if load started; take it right away (load ramps over ~10 s)
jcmd $VP GC.heap_dump "$R/idle.hprof" > "$R/dump-idle.log" 2>&1; date +%s%3N >> "$R/dump-idle.log"
for _ in $(seq 600); do
  k=$(awk -F, 'END{print $10}' "$R/samples.csv" 2>/dev/null)
  [ -n "$k" ] && [ "$k" != NA ] && [ "$k" -gt $((440*1048576)) ] 2>/dev/null && { jcmd $VP GC.heap_dump -all "$R/ceiling.hprof" > "$R/dump-ceiling.log" 2>&1; echo "K=$k $(date +%s%3N)" >> "$R/dump-ceiling.log"; break; }
  kill -0 $AP 2>/dev/null || break; sleep 0.3
done
wait $AP; tail -1 /mydata/c1r4/runs/$NAME.armlog
