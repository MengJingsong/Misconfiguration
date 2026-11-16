#!/usr/bin/env bash
# S2 batch 1 (amendment A1): endpoint x3, rate-capped control x3, CL=LOCAL_ONE intervention x3, interleaved.
cd /mydata/s2-evidence; export FILL=0 FLUSH=0 STALL=0 LOAD=90
for r in 1 2 3; do
  ./arm.sh E-blob-2G-r$r blob 2G 2>&1 | tail -1
  RATE=2000 ./arm.sh ctl-rate-2G-r$r blob 2G 2>&1 | tail -1
  CL=LOCAL_ONE ./arm.sh int-lone-2G-r$r blob 2G 2>&1 | tail -1
done
