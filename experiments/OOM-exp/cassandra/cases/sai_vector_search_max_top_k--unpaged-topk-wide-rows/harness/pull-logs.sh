#!/usr/bin/env bash
# B21 (run on pc96): copy the small per-lifetime files from ms0604:/mydata/s4/b21/out/ into the case's logs/ folder;
# optionally copy one lifetime's hprof to pc96:/mydata/b21-dumps/ for analysis (keeps the node's CPU for the runs).
#   pull-logs.sh [hprof <label>]
C=$(cd "$(dirname "$0")/.." && pwd)
rsync -a ms0604:/mydata/s4/b21/out/ "$C/logs/"
rsync -a ms0604:/mydata/s4/b21/batch.outcomes "$C/logs/batch.outcomes" 2>/dev/null
if [ "${1:-}" = hprof ]; then mkdir -p /mydata/b21-dumps/$2; rsync -a "ms0604:/mydata/s4/b21/runs/$2/*.hprof" /mydata/b21-dumps/$2/; ls -la /mydata/b21-dumps/$2; fi
