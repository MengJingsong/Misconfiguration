#!/usr/bin/env bash
# Applies the relaxed guardrails oom-exp/exp1 needs (see
# ../oom-exp/exp1/README.md) via build-cassandra-dist/step2b.sh on every
# node, then stops and restarts the cluster so the new config takes
# effect. Node addressing (step2.sh) must already have been applied --
# run build-cluster.sh first if this is a fresh cluster.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

echo "== Applying relaxed guardrails on every node (parallel) =="
pids=()
for idx in "${NODE_INDEXES[@]}"; do
  ( echo "-- node${idx} (${SSH_HOST[$idx]}) --"
    ssh_node "$idx" "bash ${REMOTE_SCRIPTS_DIR}/build-cassandra-dist/step2b.sh" ) &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done

echo
echo "== Restarting cluster to pick up the new config =="
"$SCRIPT_DIR/stop-cluster.sh"
"$SCRIPT_DIR/start-cluster.sh"

echo
echo "== Verifying deployed heap size on node0 =="
ssh_node 0 "${REMOTE_CASSANDRA_HOME}/bin/nodetool info | grep -i 'heap memory'"
