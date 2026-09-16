#!/usr/bin/env bash
# Shared configuration for the Cassandra cluster orchestrator scripts.
#
# Intended to run from a control machine (e.g. WSL) that has SSH access to
# the experiment nodes but does NOT have /proj mounted. The scripts here
# SSH out and drive the per-node build scripts that live in
# $REMOTE_SCRIPTS_DIR on every node (shared via NFS across the cluster,
# not the control machine).
#
# Path values (PROJ, REPO_ROOT, hostnames, IPs, ...) now live in
# config/environment.sh (external refs) and config/repo_layout.sh (local
# refs) at the repo root -- see those files, and config/environment.sh.example
# if config/environment.sh doesn't exist yet on this machine.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT_GUESS="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=/dev/null
source "$REPO_ROOT_GUESS/config/environment.sh"
# shellcheck source=/dev/null
source "$REPO_ROOT_GUESS/config/repo_layout.sh"

declare -A SSH_HOST=(
  [0]="${PREFIX[0]}.${POSTFIX}"
  [1]="${PREFIX[1]}.${POSTFIX}"
  [2]="${PREFIX[2]}.${POSTFIX}"
  [3]="${PREFIX[3]}.${POSTFIX}"
)

# Absolute path -- do NOT rely on sourcing ~/.bashrc over ssh for this.
# Ubuntu's default ~/.bashrc returns early for non-interactive shells
# (see the "case $- in *i*) ;; *) return;; esac" guard near its top),
# so exports appended to it by remotes/step1.sh never actually apply
# when invoked as `ssh host 'source ~/.bashrc; ...'`.
REMOTE_SCRIPTS_DIR="$REPO_ROOT/cassandra"
REMOTE_CASSANDRA_HOME="$MYDATA_CASSANDRA_HOME"

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
