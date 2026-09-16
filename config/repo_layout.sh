#!/usr/bin/env bash
# Local refs: paths relative to $REPO_ROOT (this repo's own root). These
# only change if folders are renamed/moved *within* this repo. Sourced
# after config/environment.sh, which defines REPO_ROOT.

CASSANDRA_DIR="$REPO_ROOT/cassandra"
HADOOP_DIR="$REPO_ROOT/hadoop"

BUILD_CASSANDRA_DIST_DIR="$CASSANDRA_DIR/build-cassandra-dist"
ORCHESTRATOR_DIR="$BUILD_CASSANDRA_DIST_DIR/orchestrator"
REMOTES_DIR="$BUILD_CASSANDRA_DIST_DIR/remotes"

OOM_EXP_DIR="$CASSANDRA_DIR/oom-exp/exp1"
OOM_EXP_ORCHESTRATOR_DIR="$OOM_EXP_DIR/orchestrator"
OOM_EXP_REMOTES_DIR="$OOM_EXP_DIR/remotes"

HADOOP_BUILD_SRC_DIR="$HADOOP_DIR/build-hadoop-src"
