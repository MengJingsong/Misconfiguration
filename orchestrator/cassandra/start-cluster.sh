#!/usr/bin/env bash
# Starts Cassandra on every node via build-cassandra-dist/step3.sh, one
# node at a time (seeds first, in SEED_INDEXES order, then the rest),
# each waited on until it reports itself Up/Normal in `nodetool status`
# before the next one starts.
#
# This has to be fully sequential, not just "seeds before non-seeds": on
# a brand new cluster, ANY two nodes bootstrapping at the same time can
# race on token allocation over gossip and pick the same token, which
# crashes the loser with "Bootstrap Token collision" (seen in practice
# when node2 and node3 were started together here). Safe to re-run --
# step3.sh skips nodes where Cassandra is already running.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

READY_TIMEOUT=180   # seconds to wait for each node to report UN
POLL_INTERVAL=5

start_node() {
  local idx="$1"
  ssh_node "$idx" "bash ${REMOTE_SCRIPTS_DIR}/build-cassandra-dist/step3.sh"
}

# Waits until `nodetool status` (run on the node itself, via SSH) reports
# this node's own cluster IP as "UN" (Up/Normal) -- not just that the JMX
# port has come up, which happens earlier and doesn't mean the node has
# actually joined the ring.
wait_for_ready() {
  local idx="$1"
  local ip="${CLUSTER_IP[$idx]}"
  local waited=0
  echo -n "  waiting for node${idx} (${SSH_HOST[$idx]}, ${ip}) to report UN ..."
  while (( waited < READY_TIMEOUT )); do
    if ssh_node "$idx" "${REMOTE_CASSANDRA_HOME}/bin/nodetool status" 2>/dev/null \
        | grep -qE "^UN[[:space:]]+${ip}[[:space:]]"; then
      echo " up (${waited}s)"
      return 0
    fi
    sleep "$POLL_INTERVAL"
    waited=$((waited + POLL_INTERVAL))
    echo -n "."
  done
  echo " TIMEOUT after ${READY_TIMEOUT}s"
  return 1
}

fail_hint() {
  local idx="$1"
  echo "node${idx} (${SSH_HOST[$idx]}) failed to come up in time -- check ${REMOTE_CASSANDRA_HOME}/logs/system.log there" >&2
}

# Seeds first (in SEED_INDEXES order), then the remaining nodes -- all
# strictly one at a time.
ordered_idxs=("${SEED_INDEXES[@]}")
for idx in "${NODE_INDEXES[@]}"; do
  is_seed "$idx" && continue
  ordered_idxs+=("$idx")
done

echo "== Starting nodes one at a time (seeds first: ${SEED_INDEXES[*]}) =="
for idx in "${ordered_idxs[@]}"; do
  echo "-- node${idx} (${SSH_HOST[$idx]}) --"
  start_node "$idx"
  wait_for_ready "$idx" || { fail_hint "$idx"; exit 1; }
done

echo
echo "== Cluster status (from node${NODE_INDEXES[0]}) =="
ssh_node "${NODE_INDEXES[0]}" "${REMOTE_CASSANDRA_HOME}/bin/nodetool status"
