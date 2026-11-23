#!/bin/bash
# B23: after budget.sh, repeat the failing budgets x2 (design §2.9, "if time allows"; 15,872 MiB too if it failed),
# then condition X (design §2.8): X-T x1 (original), X-I x3 (fixed build), 1 MiB values, N 20,000.
S=/mydata/s4/b23/seq.log
until grep -q "budget done" $S; do sleep 10; done
specs=("B4G-2 4G T 200000" "B4G-3 4G T 200000" "B8G-2 8G T 400000" "B8G-3 8G T 400000")
[ -s /mydata/s4/b23/B15872M/logs/oom-grep.txt ] && specs+=("B15872M-2 15872M T 400000" "B15872M-3 15872M T 400000")
specs+=("XT1 2G T 20000 1048576" "XI1 2G I 20000 1048576" "XI2 2G I 20000 1048576" "XI3 2G I 20000 1048576")
bash /mydata/s4/b23/harness/seq.sh "${specs[@]}"
