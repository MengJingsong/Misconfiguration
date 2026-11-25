#!/usr/bin/env bash
# chain 2: frozen rule "mixed outcome (1/3) -> two repeats (n/5)" for the A-2 control C1 at 8 GiB
while pgrep -f "harness/series.sh" > /dev/null || pgrep -f "harness/after1.sh" > /dev/null; do sleep 10; done
bash /mydata/s4/u16/harness/series.sh "C1x8-4 base 8G 1 fixed:32 150" "C1x8-5 base 8G 1 fixed:32 150"
