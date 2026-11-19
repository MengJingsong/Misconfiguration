#!/usr/bin/env bash
# U9 setup on pc91 (stage 2). Copies the built 5.0.9 tree out of /mydata/s4/cassandra-base (read only), keeps a
# pristine conf, installs this harness on the node. Run from the controller: ssh pc91 bash -s < setup.sh is not used;
# the harness dir is scp'd to $ROOT/harness first, then this runs on pc91.
set -euo pipefail
ROOT=/mydata/s4/u9-w4
mkdir -p "$ROOT/runs"
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
chmod +x "$ROOT"/harness/*.sh
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar
echo setup ok
