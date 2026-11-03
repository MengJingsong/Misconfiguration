#!/usr/bin/env bash
# Cluster tier (B3e, amended 2026-10-24), run 1: t = 0.11, 0.33, 0.6 (phase 1 then phase 2, 256 MiB); the C4 positive control
# (128 MiB, t = 0.11, phase 2 only); then startup with 0.005. One node at a time.
H=$(cd "$(dirname "$0")" && pwd)
"$H/cluster-run.sh" k011 0.11 256MiB both || exit 1
"$H/cluster-run.sh" k033 0.33 256MiB both || exit 1
"$H/cluster-run.sh" k060 0.6 256MiB both || exit 1
"$H/cluster-run.sh" ctl-hs128 0.11 128MiB p2only || exit 1
"$H/cluster-run.sh" startfail-0005 0.005 256MiB startfail || exit 1
ps -eo command | grep '[C]assandraDaemon' && echo "WARNING: CassandraDaemon left" || echo "chain done; no CassandraDaemon left"
