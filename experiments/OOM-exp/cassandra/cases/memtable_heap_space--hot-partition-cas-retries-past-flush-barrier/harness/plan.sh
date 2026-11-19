#!/usr/bin/env bash
# B18 stage-2 sequence runner (from C6's plan.sh): runs each line of a plan file ("<run.py args>") in order; no new lifetime
# starts after 17:20 America/New_York (design §2.7 stopping budget). A line whose lifetime fails is logged and the plan continues.
# usage: plan.sh <planfile>   (launched detached: ( setsid nohup bash plan.sh <plan> < /dev/null > ... 2>&1 & ))
W=/mydata/s4/b18-w4
H=$W/harness
P=$1
while IFS= read -r line; do
  [ -z "$line" ] && continue
  case "$line" in \#*) continue;; esac
  now=$(TZ=America/New_York date +%H%M)
  if [ "$now" -ge 1720 ]; then echo "$(date +%s) SKIP (after 17:20 NY): $line"; continue; fi
  if [ -e "$W/plan.halt" ]; then echo "$(date +%s) SKIP (plan.halt): $line"; continue; fi
  echo "$(date +%s) START $line"
  python3 -I $H/run.py $line
  echo "$(date +%s) END rc=$? $line"
done < "$P"
echo "$(date +%s) PLAN DONE"
