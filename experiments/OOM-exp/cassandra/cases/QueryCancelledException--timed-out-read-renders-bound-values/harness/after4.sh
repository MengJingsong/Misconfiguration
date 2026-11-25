#!/usr/bin/env bash
# chain 4 (amendment A-3, supplementary): the frozen O4 remedy "smaller N for the control": base, 8 GiB, k_c = 2, N = 8, 150 s x3
while pgrep -f "harness/series.sh" > /dev/null || pgrep -f "harness/after[123].sh" > /dev/null; do sleep 10; done
bash /mydata/s4/u16/harness/series.sh "CN8-1 base 8G 2 fixed:8 150" "CN8-2 base 8G 2 fixed:8 150" "CN8-3 base 8G 2 fixed:8 150"
