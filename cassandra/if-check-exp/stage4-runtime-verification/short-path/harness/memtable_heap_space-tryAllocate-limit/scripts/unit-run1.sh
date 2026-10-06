#!/bin/bash
set -x
cd ~/short-run/memtable_heap_space-tryAllocate-limit/unit/cass-src-unit
echo "== parse check: ant build-test =="
ant build-test
BUILD_RC=$?
echo "build-test rc=$BUILD_RC"
if [ $BUILD_RC -ne 0 ]; then
  echo "STOP: parse check failed"
  exit 1
fi

echo "== known-answer check: run testHardLimitBlocks =="
ant test -Dtest.name=MemtablePoolLimitTest -Dtest.methods=testHardLimitBlocks
echo "testHardLimitBlocks rc=$?"

echo "== run testDiscardingOvershoots =="
ant test -Dtest.name=MemtablePoolLimitTest -Dtest.methods=testDiscardingOvershoots
echo "testDiscardingOvershoots rc=$?"
