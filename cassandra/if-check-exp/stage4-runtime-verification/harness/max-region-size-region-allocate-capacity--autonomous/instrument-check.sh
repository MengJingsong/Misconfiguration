#!/usr/bin/env bash
# Instrument check for the three trees of max-region-size-region-allocate-capacity--autonomous: the compiled MAX_REGION_SIZE in the
# class dir AND in the jar the node runs from, the git diff of each tree against its baseline, and that no ant/java of another case touches them.
for v in "" -m256 -m4096; do
  C=$HOME/s4-b7-mr$v
  echo "tree $C: git diff --stat vs cassandra-5.0.9:"; git -C $C diff --stat cassandra-5.0.9 -- src | tail -3
  echo "  classes: $(javap -p -constants -cp $C/build/classes/main org.apache.cassandra.utils.memory.NativeAllocator | grep 'MAX_REGION_SIZE')"
  J=$(ls $C/build/apache-cassandra-5.0.9*.jar | head -1)
  echo "  jar $(basename $J): $(javap -p -constants -cp $J org.apache.cassandra.utils.memory.NativeAllocator | grep 'MAX_REGION_SIZE')"
done
