#!/usr/bin/env bash
# C6: build small per-lifetime excerpts on pc91 under /mydata/s4/c6-w2/excerpts/<label>/ (copied to the case folder's logs/).
# usage: excerpts.sh <label> ...
W=/mydata/s4/c6-w2
for L in "$@"; do
  S=$W/logs/$L; O=$W/excerpts/$L; mkdir -p $O
  cp $S/summary.json $O/ 2>/dev/null
  python3 -c "import json; s=json.load(open('$S/summary.json')); s.get('oom',{}).update(stdout_lines=[l for l in s.get('oom',{}).get('stdout_lines',[]) if 'JVM Arguments' not in l and 'CompileCommand' not in l]) if 'oom' in s else None; json.dump(s, open('$O/summary.json','w'), indent=1)" 2>/dev/null
  cp $S/scan-*.json $S/yaml.diff $S/env.diff $S/memory.events $O/ 2>/dev/null
  [ -f $S/client.csv ] && { head -15 $S/client.csv; echo ...; tail -8 $S/client.csv; } > $O/client-excerpt.csv
  [ -f $S/sampler.csv ] && { head -1 $S/sampler.csv; grep -v ERR $S/sampler.csv | tail -n +2 | awk -F, 'NR%5==1' | tail -40; echo "# last valid rows:"; grep -v ERR $S/sampler.csv | tail -4; } > $O/sampler-excerpt.csv
  [ -f $S/rss.csv ] && { head -1 $S/rss.csv; awk -F, 'NR>1 && NR%10==2' $S/rss.csv | tail -20; tail -3 $S/rss.csv; } > $O/rss-excerpt.csv
  [ -f $S/stdout.txt ] && grep -E "java.lang.OutOfMemoryError|Dumping heap|Heap dump file|kill -9|^Killed" $S/stdout.txt > $O/stdout-oom.txt
  [ -f $S/system.log ] && grep -E "^(ERROR|WARN)|Enqueuing flush of ks\.|Replaying|replayed mutations" $S/system.log | cut -c1-400 | head -40 > $O/system-log-excerpt.txt
  gcs() { cat $S/gc.log* | grep -E "Pause (Full|Young)" | awk -F'[][]' '{print $4"\t"$0}' | sort -n | cut -f2-; }
  ls $S/gc.log* >/dev/null 2>&1 && { gcs | head -3; echo "... (Pause Full count: $(gcs | grep -c 'Pause Full'); first Full: $(gcs | grep -m1 'Pause Full' | cut -c1-60))"; gcs | tail -12; } > $O/gc-excerpt.txt
  for h in $S/hist-*.txt; do [ -f "$h" ] && head -14 "$h" > $O/$(basename $h .txt)-head.txt && tail -1 "$h" >> $O/$(basename $h .txt)-head.txt; done
  cp $S/jvm-cmdline.txt $O/ 2>/dev/null
  [ -f $S/acks.csv ] && wc -l < $S/acks.csv > $O/acks-lines.txt
done
