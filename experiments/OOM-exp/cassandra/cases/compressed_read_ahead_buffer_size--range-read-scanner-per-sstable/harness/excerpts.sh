#!/bin/bash
# C9: copy small excerpts of one run from pc99 into <case folder>/logs/<run-id>/ (full logs stay on pc99:/mydata/s4/c9-w4/runs/<run-id>/)
# usage: excerpts.sh <run-id>
set -u
R=$1
CASE=$(cd "$(dirname "$0")/.." && pwd)
D=$CASE/logs/$R
mkdir -p "$D"
ssh pc99 "cd /mydata/s4/c9-w4/runs/$R && grep -v '^  INFO\|^  WARN' summary.txt" > "$D/summary.txt"
ssh pc99 "cd /mydata/s4/c9-w4/runs/$R && cat notes.txt jvmargs.txt yaml.diff 2>/dev/null; cat client/client.txt 2>/dev/null; cat trace.txt 2>/dev/null | grep -i 'seq scan\|Merged data\|Read' | head -5" > "$D/meta.txt"
ssh pc99 "cd /mydata/s4/c9-w4/runs/$R && t=\$(cat t_load.txt); head -1 samples.csv; awk -F, -v t=\$t 'NR>1 && \$1>=t-2000' samples.csv | tail -75" > "$D/samples-last15s.csv"
ssh pc99 "cd /mydata/s4/c9-w4/runs/$R && tail -15 gc.log 2>/dev/null; grep -h 'Pause Full\|To-space' gc.log* 2>/dev/null | tail -5" > "$D/gc-tail.txt"
ssh pc99 "journalctl -k --since '-6h' 2>/dev/null | grep -i 'oom-kill\|out of memory' | tail -3; dmesg 2>/dev/null | grep -i oom | tail -3" > "$D/kernel-oom-grep.txt" 2>&1
ls "$D"
