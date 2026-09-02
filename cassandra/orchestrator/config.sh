#!/usr/bin/env bash
# Shared configuration for the Cassandra cluster orchestrator scripts.
#
# Intended to run from a control machine (e.g. WSL) that has SSH access to
# the experiment nodes but does NOT have /proj mounted. The scripts here
# SSH out and drive the per-node build scripts that already live in
# /proj/misconfiguration-PG0/cassandra on every node (shared via NFS across
# the cluster, not the control machine).

set -euo pipefail

SSH_USER="jason92"

# Domain suffix shared by every node's physical hostname.
POSTFIX="cloudlab.umass.edu"

# Physical hostnames (stable across experiment swaps, unlike the
# node0/node1/... aliases which only resolve inside the experiment LAN).
# Index order must match NODE_INDEXES below.
PREFIX=('pc66' 'pc69' 'pc65' 'pc99')

# Node index -> SSH hostname (external, reachable from the control
# machine) and internal cluster LAN IP (used for Cassandra
# listen/broadcast/seed addresses -- only routable inside the experiment).
NODE_INDEXES=(0 1 2 3)
declare -A SSH_HOST=(
  [0]="${PREFIX[0]}.${POSTFIX}"
  [1]="${PREFIX[1]}.${POSTFIX}"
  [2]="${PREFIX[2]}.${POSTFIX}"
  [3]="${PREFIX[3]}.${POSTFIX}"
)
# Experiment-LAN IP per node, last discovered by check-ips.sh on 2026-09-01T20:13Z.
declare -A CLUSTER_IP=(
  [0]="10.10.1.1"
  [1]="10.10.1.2"
  [2]="10.10.1.3"
  [3]="10.10.1.4"
)

# Which node indexes act as Cassandra seeds.
SEED_INDEXES=(0 1)

REMOTE_SCRIPTS_DIR="/proj/misconfiguration-PG0/cassandra"
# Absolute path -- do NOT rely on sourcing ~/.bashrc over ssh for this.
# Ubuntu's default ~/.bashrc returns early for non-interactive shells
# (see the "case $- in *i*) ;; *) return;; esac" guard near its top),
# so the CASSANDRA_HOME export appended by step1.sh never actually runs
# when invoked as `ssh host 'source ~/.bashrc; ...'`.
REMOTE_CASSANDRA_HOME="/mydata/apache-cassandra-5.0.7"

is_seed() {
  local idx="$1"
  for seed in "${SEED_INDEXES[@]}"; do
    [[ "$idx" == "$seed" ]] && return 0
  done
  return 1
}

ssh_node() {
  local idx="$1"; shift
  ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "${SSH_USER}@${SSH_HOST[$idx]}" "$@"
}

seeds_string() {
  local s=""
  for idx in "${SEED_INDEXES[@]}"; do
    s+="${CLUSTER_IP[$idx]}:7000,"
  done
  echo "${s%,}"
}
