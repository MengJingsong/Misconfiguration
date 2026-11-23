#!/usr/bin/env bash
# U14: small per-lifetime excerpts on the node -> /mydata/s4/u14/excerpts/ (copied into the case folder's logs/).
W=/mydata/s4/u14; O=$W/excerpts; mkdir -p $O
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
    echo "== client.csv first/last"; sed -n 2,3p $d/client.csv; tail -4 $d/client.csv | cut -c1-300;
    echo "== memory.events"; cat $d/memory.events 2>/dev/null;
    echo "== MaxDirectMemorySize / heap"; grep -oE "\-XX:MaxDirectMemorySize=\S+|-Xm[sx]\S+" $d/jvm-cmdline.txt | sort -u; } > $O/$L-excerpt.txt
done
ls -la $O
