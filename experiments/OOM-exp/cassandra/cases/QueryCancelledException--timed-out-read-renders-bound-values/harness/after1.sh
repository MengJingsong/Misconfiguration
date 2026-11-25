#!/usr/bin/env bash
# chain: wait for the running series, then run the H0 = 8 GiB arms (incl. amendment A-2 control C1 at k=1) and the first budget step
while pgrep -f "harness/series.sh" > /dev/null; do sleep 10; done
bash /mydata/s4/u16/harness/series.sh "T8-1 base 8G 4 fixed:32 150" "T8-2 base 8G 4 fixed:32 150" "T8-3 base 8G 4 fixed:32 150" "C8-1 base 8G 2 fixed:32 150" "C8-2 base 8G 2 fixed:32 150" "C8-3 base 8G 2 fixed:32 150" "C1x8-1 base 8G 1 fixed:32 150" "C1x8-2 base 8G 1 fixed:32 150" "C1x8-3 base 8G 1 fixed:32 150" "I8-1 iv 8G 4 fixed:32 150" "I8-2 iv 8G 4 fixed:32 150" "I8-3 iv 8G 4 fixed:32 150" "T16-1 base 15872M 4 fixed:32 600"
