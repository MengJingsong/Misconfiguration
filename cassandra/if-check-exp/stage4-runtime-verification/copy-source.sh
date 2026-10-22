#!/usr/bin/env bash
# Copy the pinned Cassandra source (this repository's cassandra/cassandra-5.0.9/,
# or $CASSANDRA_SRC) to a new local working tree, and give that tree a one-commit
# git baseline tagged cassandra-5.0.9, so `git describe --tags`, `git diff` and
# `git checkout -- <file>` work there as they did in a clone. Never build in the
# repository's copy itself (environment.md section 2).
#
# Usage: copy-source.sh <dest-dir>     (dest must not exist yet)
set -euo pipefail
DEST=${1:?usage: copy-source.sh <dest-dir>}
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${CASSANDRA_SRC:-$HERE/../../cassandra-5.0.9}
[ -f "$SRC/build.xml" ] || { echo "no Cassandra source at $SRC" >&2; exit 1; }
grep -q 'name="base.version" value="5.0.9"' "$SRC/build.xml" || { echo "$SRC is not 5.0.9" >&2; exit 1; }
[ ! -e "$DEST" ] || { echo "$DEST already exists" >&2; exit 1; }
mkdir -p "$DEST"
rsync -a "$SRC/" "$DEST/"
git -C "$DEST" init -q
git -C "$DEST" add -Af .   # -f: upstream tracks some files its own .gitignore matches
git -C "$DEST" -c user.name=stage4 -c user.email=stage4@localhost commit -qm 'apache/cassandra cassandra-5.0.9 (copied from the Misconfiguration repository)'
git -C "$DEST" tag cassandra-5.0.9
echo "copied $SRC -> $DEST ($(git -C "$DEST" describe --tags))"
