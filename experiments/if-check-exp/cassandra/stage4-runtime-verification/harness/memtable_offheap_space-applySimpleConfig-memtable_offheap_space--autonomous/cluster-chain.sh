#!/usr/bin/env bash
# Cluster tier (B3e, amended 2026-10-24), run 1: (a) 64 MiB, 256 MiB, unset; (b); (c); then the B3h control. One node at a time.
H=$(cd "$(dirname "$0")" && pwd)
"$H/cluster-run.sh" a-k64 offheap_objects 64MiB || exit 1
"$H/cluster-run.sh" a-k256 offheap_objects 256MiB || exit 1
"$H/cluster-run.sh" a-kunset offheap_objects unset || exit 1
"$H/cluster-run.sh" b-buffers0 offheap_buffers 0MiB || exit 1
"$H/cluster-run.sh" c-objects0 offheap_objects 0MiB stall || exit 1
"$H/cluster-run.sh" ctl-heap64 heap_buffers 64MiB || exit 1
ps -eo command | grep '[C]assandraDaemon' && echo "WARNING: CassandraDaemon left" || echo "chain done; no CassandraDaemon left"
