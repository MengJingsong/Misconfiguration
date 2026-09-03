#!/usr/bin/env bash
# Stops Cassandra on every node via build-cassandra-dist/step4.sh, in
# parallel (no bootstrap/gossip race to worry about on shutdown, unlike
# start-cluster.sh). Idempotent -- step4.sh no-ops on nodes already down.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

echo "== Stopping nodes (parallel) =="
pids=()
for idx in "${NODE_INDEXES[@]}"; do
  ( echo "-- node${idx} (${SSH_HOST[$idx]}) --"
    ssh_node "$idx" "bash ${REMOTE_SCRIPTS_DIR}/build-cassandra-dist/step4.sh" ) &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done

echo "All nodes stopped."
