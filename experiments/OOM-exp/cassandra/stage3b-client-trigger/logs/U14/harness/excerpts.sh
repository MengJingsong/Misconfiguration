#!/usr/bin/env bash
# U14 (2026-11-23: + shutdown lines, tail-per-minute, trimmed hist, session, summary): small per-lifetime excerpts on the node -> /mydata/s4/u14/excerpts/ (copied into the case folder's logs/).
W=/mydata/s4/3b-U14; O=${OUT:-$W/excerpts}; mkdir -p $O   # OUT added 2026-11-23
python3 $W/harness/analyze.py $W/logs "$@" > $O/analyze.jsonl
for L in "$@"; do
  d=$W/logs/$L; [ -d $d ] || continue
  python3 -c "
import json,sys
for l in open('$d/checkpoints.jsonl'):
    c=json.loads(l); c.pop('top40',None); print(json.dumps(c))" > $O/$L-checkpoints.jsonl 2>/dev/null
  for t in oom end; do [ -f $d/scan-$t.json ] && cp $d/scan-$t.json $O/$L-scan-$t.json; done
  { echo "== stdout.txt (OOM lines and tail)"; grep -nE "java.lang.OutOfMemoryError|Dumping heap|Heap dump file|kill -9" $d/stdout.txt | grep -v CompileCommand | head;
    echo "== system.log last GCInspector lines"; grep GCInspector $d/system.log | tail -3 | cut -c1-300;
    echo "== system.log shutdown (SIGTERM by the harness, if any)"; grep -E "Stop listening for CQL|Announcing shutdown|shutdown complete" $d/system.log | cut -c1-200;
    echo "== client.csv first/last"; sed -n 2,3p $d/client.csv; tail -4 $d/client.csv | cut -c1-300;
    echo "== memory.events"; cat $d/memory.events 2>/dev/null;
    echo "== MaxDirectMemorySize / heap"; grep -oE "\-XX:MaxDirectMemorySize=\S+|-Xm[sx]\S+" $d/jvm-cmdline.txt | sort -u; } > $O/$L-excerpt.txt
  # 2026-11-23: per-minute tail, gc.log STW share, trimmed histograms (top 50 classes of s0, last n-checkpoint, end), small session log
  python3 $W/harness/tailmin.py $d ${TAILMIN:-15} > $O/$L-tail-per-minute.txt 2>/dev/null
  python3 $W/harness/gcshare.py $d 10 > $O/$L-gcshare.txt 2>/dev/null
  mkdir -p $O/hist; last=$(ls $d | grep -E '^hist-n[0-9]+-2.txt$' | sort -t n -k2 -n | tail -1)
  for h in hist-s0-2.txt $last hist-end-2.txt; do [ -f $d/$h ] && head -55 $d/$h > $O/hist/$L-$h; done
  cut -c1-1500 $d/session.log > $O/$L-session.log
  cp $d/summary.json $O/$L-summary.json
done
ls -la $O
