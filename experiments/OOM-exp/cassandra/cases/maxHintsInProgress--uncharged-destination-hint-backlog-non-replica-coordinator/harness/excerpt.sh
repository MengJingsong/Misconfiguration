#!/bin/bash
# B23: collect small excerpts of a run into /mydata/s4/b23/excerpts/<label>/ (then copied to the case folder's logs/). usage: bash excerpt.sh <label>...
for L in "$@"; do
  R=/mydata/s4/b23/$L; O=/mydata/s4/b23/excerpts/$L; mkdir -p $O
  cp $R/logs/driver.log $R/logs/oom-grep.txt $O/ 2>/dev/null
  [ -f $R/logs/hprofhist.txt ] && cp $R/logs/hprofhist.txt $O/
  cp $R/n1/logs/conf.diff $O/n1-conf.diff 2>/dev/null
  grep -o -- '-Xm[sx][^ ]*\|-XX:MaxDirectMemorySize=[^ ]*\|-XX:+Use[A-Za-z0-9]*GC\|-XX:OnOutOfMemoryError=[^ ]* [^ ]* [^ ]*' $R/logs/n1-cmdline.txt > $O/n1-cmdline-excerpt.txt 2>/dev/null
  # poll: header + every 5th line + last 5
  { head -1 $R/logs/poll1.log; awk 'NR>1 && NR%5==0' $R/logs/poll1.log; tail -5 $R/logs/poll1.log; } > $O/poll1-every5s.log
  awk 'NR%5==1' $R/logs/hints-rss.log > $O/hints-rss-every5s.log
  grep -h -B4 -A8 '^java.lang.OutOfMemoryError' $R/n1/logs/stdout.txt 2>/dev/null | head -40 > $O/n1-oom-context.txt
  grep -E 'GCInspector' $R/n1/logs/system.log | tail -8 > $O/n1-gcinspector-tail.txt
  tail -22 $R/logs/stress-stdout.txt > $O/stress-tail.txt
  grep -c 'Pause Full' $R/n1/logs/gc.log > $O/n1-fullgc-count.txt
  python3 -I /mydata/s4/b23/harness/summary.py $R > $O/summary.txt
  [ -f $R/logs/jstack-K5120.txt ] && { grep -B12 'locked <.*HintsBufferPool' $R/logs/jstack-K5120.txt | head -14; echo; echo "threads BLOCKED waiting to lock HintsBufferPool: $(grep -c 'waiting to lock <.*HintsBufferPool' $R/logs/jstack-K5120.txt)"; } > $O/jstack-K5120-excerpt.txt
  [ -f $R/hist/K8000.txt ] && head -15 $R/hist/K8000.txt > $O/hist-K8000-head.txt && grep -E 'StorageProxy\$7|db\.Mutation |Total' $R/hist/K8000.txt >> $O/hist-K8000-head.txt
done
