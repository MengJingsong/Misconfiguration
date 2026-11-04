#!/usr/bin/env bash
# Instrument check (not a reading): the tree is stock, the two REGION_SIZE variants differ from SlabAllocator.java by exactly line 51.
C=${CASSANDRA_HOME:-$HOME/s4-b7-sr7}; LG=$HOME/s4-b7-sr7-logs
git -C "$C" status --short | head -5; echo "tree diff vs baseline: $(git -C "$C" diff --stat | tail -1)"
for v in v512 v2048; do echo "$v diff:"; cat "$LG/$v.diff"; javap -p -constants -cp "$LG/$v" org.apache.cassandra.utils.memory.SlabAllocator | grep REGION_SIZE; done
javap -p -constants -cp "$C/build/classes/main" org.apache.cassandra.utils.memory.SlabAllocator | grep -E 'REGION_SIZE|MAX_CLONED_SIZE'
