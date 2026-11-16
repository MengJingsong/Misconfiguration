#!/usr/bin/env bash
# sequential arm queue: each line "ENV... NAME N RATE DIRECT"
H=/mydata/s1/harness
while read -r line; do [ -z "$line" ] && continue; [ -f /mydata/s1/STOP ] && break; echo "[$(date +%T)] $line"; env $line 2>&1 | tail -1; done
