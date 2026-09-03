#!/usr/bin/env bash
# Installs Cassandra 5.0.7 on every node (step1) and writes each node's
# cassandra.yaml with the right addresses/seeds (step2). Safe to re-run.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

echo "== Step 1: build/install Cassandra on node0 first (primes the shared tarball) =="
ssh_node 0 "bash ${REMOTE_SCRIPTS_DIR}/build-cassandra-dist/remotes/step1.sh"

echo "== Step 1: build/install Cassandra on the remaining nodes (parallel) =="
pids=()
for idx in "${NODE_INDEXES[@]}"; do
  [[ "$idx" == "0" ]] && continue
  ssh_node "$idx" "bash ${REMOTE_SCRIPTS_DIR}/build-cassandra-dist/remotes/step1.sh" &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done

SEEDS="$(seeds_string)"
echo "== Step 2: configure cassandra.yaml on every node (seeds=${SEEDS}) =="
for idx in "${NODE_INDEXES[@]}"; do
  ssh_node "$idx" "bash ${REMOTE_SCRIPTS_DIR}/build-cassandra-dist/remotes/step2.sh \"${SEEDS}\" \"${CLUSTER_IP[$idx]}\""
done

echo "Build complete. Next: run start-cluster.sh"
