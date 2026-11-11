#!/usr/bin/env bash
# Set up one node for Jingsong's Hadoop stage 4 (environment.md §1-3): JDK 8 + Maven if absent,
# copy the pinned source to /mydata/jingsong-s4/hadoop-base, full dist build (never resumed with -rf).
# Usage (on the node): setup-node.sh            Log: /mydata/jingsong-s4/build-base-full.log
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=/mydata/jingsong-s4
JDK=/usr/lib/jvm/java-8-openjdk-amd64
if [ ! -x "$JDK/bin/javac" ] || ! command -v mvn >/dev/null; then
  sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openjdk-8-jdk maven
fi
[ -w "$ROOT" ] || { sudo mkdir -p "$ROOT" && sudo chown "$(id -un):$(id -gn)" "$ROOT"; }
[ -d "$ROOT/hadoop-base" ] || "$HERE/copy-source.sh" "$ROOT/hadoop-base"
cd "$ROOT/hadoop-base"
export JAVA_HOME=$JDK YARN_IGNORE_ENGINES=true
start=$(date +%s)
mvn -B install -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true -T 8 > "$ROOT/build-base-full.log" 2>&1
echo "build exit 0 in $(( $(date +%s) - start )) s" | tee "$ROOT/build-base-full.time"
D=$ROOT/hadoop-base/hadoop-dist/target/hadoop-3.4.2
"$D/bin/hadoop" version | head -1
ls "$D/share/hadoop/yarn/"*.jar | wc -l
