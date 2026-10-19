#!/usr/bin/env bash
# Environment setup on the measured node (environment.md sections 1-3).
# Installs JDK 11 + Ant, clones cassandra-5.0.9 to local disk under the run dir, builds.
# Logs every command (set -x) and its output to $RUN/logs/00-setup.log; stops at the first failure.
set -euo pipefail
RUN=~/short-run/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction
mkdir -p "$RUN/logs"
exec > >(tee -a "$RUN/logs/00-setup.log") 2>&1
set -x
date -u +%FT%TZ
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y openjdk-11-jdk ant
java -version
ant -version
which jcmd jstack
if [ ! -d "$RUN/cassandra" ]; then
  git clone --branch cassandra-5.0.9 /proj/misconfiguration-PG0/git-repos/cassandra-src "$RUN/cassandra"
fi
git -C "$RUN/cassandra" rev-parse HEAD
git -C "$RUN/cassandra" describe --tags
git -C "$RUN/cassandra" status --short | head
cd "$RUN/cassandra"
# B2a says `ant jar`; build-test is a superset needed for the unit test (environment.md section 3).
ant jar
ant build-test
date -u +%FT%TZ
echo SETUP_OK
