#!/usr/bin/env bash
# R1 recheck: run a list of arms sequentially (one per line: name budget M F workloads); check hygiene after each.
R=/mydata/oom-recheck/R1; LIST=$1
while read -r name budget M F WL; do
  [ -z "$name" ] && continue; [[ "$name" == \#* ]] && continue
  if [ -e "$R/STOP" ]; then echo "[$(date '+%F %T')] STOP file present, not starting $name"; break; fi
  echo "[$(date '+%F %T')] START $name $budget $M $F $WL"
  bash "$R/oom-run.sh" arm "$name" "$budget" "$M" "$F" "$WL" > "$R/logs/$name.out" 2>&1 < /dev/null; rc=$?
  left=$(pgrep -af '^(/usr/bin/)?java .*(org[.]apache[.]cassandra[.]service[.]CassandraDaemon|org[.]apache[.]cassandra[.]stress[.]Stress|PoolPoller)' || true)
  scopes=$(systemctl --user list-units --type=scope --no-legend 'oom-r1-*' 2>/dev/null)
  echo "[$(date '+%F %T')] END $name rc=$rc; leftover procs: ${left:-none}; scopes: ${scopes:-none}"
  echo "    $(grep -E 'dmesg kills|node (alive|GONE) at end' "$R/logs/$name/summary.txt" | tr '\n' ' ')"
  [ -n "$left" ] && { echo "leftover processes, aborting"; break; }
done < "$LIST"
echo "[$(date '+%F %T')] LIST DONE"
