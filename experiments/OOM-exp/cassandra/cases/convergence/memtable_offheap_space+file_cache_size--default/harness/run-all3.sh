#!/usr/bin/env bash
# R1V v2 (amendment 1, 2026-11-12; uses oom-run3.sh): run a list of arms sequentially (one per line: name L_MiB H_MiB M F workloads); hygiene check after each.
# v3 (2026-11-16, pc96 re-run): run dir /mydata/r1v2, oom-run3.sh, scope oom-r1v2-*, leftover check limited to this run dir (poller matched by its /mydata/r1v2/tools classpath).
# A file /mydata/r1v2/STOP stops the list before the next arm.
R=/mydata/r1v2; LIST=$1
while read -r name budget heap M F WL; do
  [ -z "$name" ] && continue; [[ "$name" == \#* ]] && continue
  if [ -e "$R/STOP" ]; then echo "[$(date '+%F %T')] STOP file present, not starting $name"; break; fi
  echo "[$(date '+%F %T')] START $name L=$budget H=$heap M=$M F=$F $WL"
  bash "$R/oom-run3.sh" arm "$name" "$budget" "$heap" "$M" "$F" "$WL" > "$R/logs/$name.out" 2>&1 < /dev/null; rc=$?
  [ -d "$R/logs/$name" ] && bash "$R/dmesg-block.sh" "$R/logs/$name" >/dev/null 2>&1
  left=$(pgrep -af '^(/usr/bin/)?java .*/mydata/r1v2/cassandra.*(org[.]apache[.]cassandra[.]service[.]CassandraDaemon|org[.]apache[.]cassandra[.]stress[.]Stress)|java -cp /mydata/r1v2/tools PoolPoller' || true)
  scopes=$(systemctl --user list-units --type=scope --no-legend 'oom-r1v2-*' 2>/dev/null)
  echo "[$(date '+%F %T')] END $name rc=$rc; leftover procs: ${left:-none}; scopes: ${scopes:-none}"
  echo "    $(grep -E 'dmesg kills|node (alive|GONE) at end' "$R/logs/$name/summary.txt" | tr '\n' ' ')"
  [ -n "$left" ] && { echo "leftover processes, aborting"; break; }
done < "$LIST"
echo "[$(date '+%F %T')] LIST DONE"
