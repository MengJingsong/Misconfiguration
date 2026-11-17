#!/usr/bin/env bash
# R1V v2 (amendment 1, 2026-11-12; uses oom-run2.sh): run a list of arms sequentially (one per line: name L_MiB H_MiB M F workloads); hygiene check after each.
# A file /mydata/r1v/STOP stops the list before the next arm.
R=/mydata/r1v; LIST=$1
while read -r name budget heap M F WL; do
  [ -z "$name" ] && continue; [[ "$name" == \#* ]] && continue
  if [ -e "$R/STOP" ]; then echo "[$(date '+%F %T')] STOP file present, not starting $name"; break; fi
  echo "[$(date '+%F %T')] START $name L=$budget H=$heap M=$M F=$F $WL"
  bash "$R/oom-run2.sh" arm "$name" "$budget" "$heap" "$M" "$F" "$WL" > "$R/logs/$name.out" 2>&1 < /dev/null; rc=$?
  [ -d "$R/logs/$name" ] && bash "$R/dmesg-block.sh" "$R/logs/$name" >/dev/null 2>&1
  left=$(pgrep -af '^(/usr/bin/)?java .*(org[.]apache[.]cassandra[.]service[.]CassandraDaemon|org[.]apache[.]cassandra[.]stress[.]Stress|PoolPoller)' || true)
  scopes=$(systemctl --user list-units --type=scope --no-legend 'oom-r1v-*' 2>/dev/null)
  echo "[$(date '+%F %T')] END $name rc=$rc; leftover procs: ${left:-none}; scopes: ${scopes:-none}"
  echo "    $(grep -E 'dmesg kills|node (alive|GONE) at end' "$R/logs/$name/summary.txt" | tr '\n' ' ')"
  [ -n "$left" ] && { echo "leftover processes, aborting"; break; }
done < "$LIST"
echo "[$(date '+%F %T')] LIST DONE"
