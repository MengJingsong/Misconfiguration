#!/usr/bin/env bash
# Cluster tier (B3e), run 1 after runbook fix 1: the three knob values in order, then the B3h off-heap control. One node at a time.
H=$(cd "$(dirname "$0")" && pwd)
"$H/cluster-run.sh" k64 64MiB || exit 1
"$H/cluster-run.sh" k256 256MiB || exit 1
"$H/cluster-run.sh" kunset unset || exit 1
"$H/cluster-run.sh" ctl-offheap64 64MiB offheap_objects 64MiB || exit 1
