#!/usr/bin/env bash
# Local refs: paths relative to $REPO_ROOT (this repo's own root). These
# only change if folders are renamed/moved *within* this repo. Sourced
# after config/environment.sh, which defines REPO_ROOT.
#
# Layout (since the multi-system restructure): experiments are
# system-agnostic and hold per-system data under <exp>/<system>/; each
# system's source, build scripts and config baseline live under
# systems/<system>/.

# --- systems (source, build tooling, config baseline) ---
SYSTEMS_DIR="$REPO_ROOT/systems"

CASSANDRA_SYS_DIR="$SYSTEMS_DIR/cassandra"
CASSANDRA_SOURCE_DIR="$CASSANDRA_SYS_DIR/source"          # pinned apache/cassandra @ cassandra-5.0.9
BUILD_CASSANDRA_DIST_DIR="$CASSANDRA_SYS_DIR/build-dist"  # 4-node cluster install/run scripts
ORCHESTRATOR_DIR="$BUILD_CASSANDRA_DIST_DIR/orchestrator"
REMOTES_DIR="$BUILD_CASSANDRA_DIST_DIR/remotes"
CASSANDRA_CONF_DIR="$CASSANDRA_SYS_DIR/conf"              # stock config baseline

HADOOP_SYS_DIR="$SYSTEMS_DIR/hadoop"
HADOOP_SOURCE_DIR="$HADOOP_SYS_DIR/source"               # pinned apache/hadoop @ rel/release-3.4.2
HADOOP_BUILD_SRC_DIR="$HADOOP_SYS_DIR/build-src"         # JDK8 + Maven + protobuf build scripts
HADOOP_CONF_DIR="$HADOOP_SYS_DIR/conf"                   # stock config baseline (to populate)

# --- experiments (system-agnostic method; per-system data under <exp>/<system>/) ---
EXPERIMENTS_DIR="$REPO_ROOT/experiments"

IFCHECK_EXP_DIR="$EXPERIMENTS_DIR/if-check-exp"
ENTRY_RESTRICTION_EXP_DIR="$EXPERIMENTS_DIR/entry-restriction-exp"
OOM_EXP_DIR="$EXPERIMENTS_DIR/OOM-exp"

# Per-system instance subtrees for each experiment, e.g.:
#   $IFCHECK_EXP_DIR/cassandra   $IFCHECK_EXP_DIR/hadoop
