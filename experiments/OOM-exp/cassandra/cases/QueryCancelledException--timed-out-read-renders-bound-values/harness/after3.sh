#!/usr/bin/env bash
# chain 3: T16-1 failed -> next budget step T31-1 (frozen order)
while pgrep -f "harness/series.sh" > /dev/null || pgrep -f "harness/after[12].sh" > /dev/null; do sleep 10; done
bash /mydata/s4/u16/harness/series.sh "T31-1 base 31744M 4 fixed:32 600"
