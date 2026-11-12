#!/usr/bin/env bash
# Continuation of batch-cycles.sh after the controller was stopped at its 30-min background limit
# during I-1 cycle 1 (that lifetime kept as runs/I-1-aborted, not used). Same arms and parameters.
H=$(cd "$(dirname "$0")" && pwd)
bash "$H/run-arm.sh" I-1 patched 5 1000000 12 200 2G 2G 4 20
for n in 2 3; do
  bash "$H/run-arm.sh" S-$n   unmod   5 1000000 12 200 2G 2G 4 20
  bash "$H/run-arm.sh" H4-$n  unmod   4 1000000 12 200 2G 2G 4 20
  bash "$H/run-arm.sh" H5s-$n unmod   5 100000  12 200 2G 2G 4 20
  bash "$H/run-arm.sh" I-$n   patched 5 1000000 12 200 2G 2G 4 20
done
echo BATCH-DONE
