#!/usr/bin/env bash
# B28: copy small excerpts of every run on $NODE (default pc82; the first attempt used pc75) into ../logs/<run>/ (summary, driver, OOME thread, owners, dump note,
# resolved values, S0 trace check, client step lines, last stdout lines, threads, df). Run on the controller.
set -u
NODE=${NODE:-pc82}
HERE=$(cd "$(dirname "$0")" && pwd); L=$HERE/../logs
for r in $(ssh $NODE 'ls /mydata/s4/b28/runs | grep -v "^series"'); do
  mkdir -p $L/$r
  ssh $NODE "cd /mydata/s4/b28/runs/$r && for f in summary.txt summary-v1.txt driver.txt oome-thread.txt owners.txt dump.txt resolved.txt conf-md5.txt s0-jmx-names.txt du-end.txt threads.txt; do [ -f \$f ] && { echo \"##### \$f\"; cat \$f; }; done; [ -f s0-traces.txt ] && { echo '##### s0-traces.txt (cut to 400 chars per line)'; cut -c1-400 s0-traces.txt; }; echo '##### client (header and step lines)'; grep '^#' client-*.txt 2>/dev/null; echo '##### stdout (OOM lines)'; grep -E 'OutOfMemoryError|Dumping heap|Heap dump file|kill -9|Starting listening' stdout.txt 2>/dev/null" > $L/$r/excerpts.txt 2>&1
done
ssh $NODE 'cat /mydata/s4/b28/runs/series-*.log' > $L/series.log
ssh $NODE 'cat /mydata/s4/b28/build.log; echo; cat /mydata/s4/b28/harness/iv.diff.applied' > $L/build.log
