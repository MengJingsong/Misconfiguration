#!/usr/bin/env bash
# Copy the pinned Hadoop source (this repository's systems/hadoop/source/, or $HADOOP_SRC) to a new
# local working tree and give it a one-commit git baseline tagged rel/release-3.4.2, so `git diff`
# and `git checkout -- <file>` work there. Never build in the repository's copy (environment.md §2).
#
# Usage: copy-source.sh <dest-dir>     (dest must not exist yet; put it on local disk, e.g. /mydata)
set -euo pipefail
DEST=${1:?usage: copy-source.sh <dest-dir>}
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${HADOOP_SRC:-$HERE/../../../../../systems/hadoop/source}
[ -f "$SRC/pom.xml" ] || { echo "no Hadoop source at $SRC" >&2; exit 1; }
grep -q '<version>3.4.2</version>' "$SRC/pom.xml" || { echo "$SRC is not 3.4.2" >&2; exit 1; }
[ ! -e "$DEST" ] || { echo "$DEST already exists" >&2; exit 1; }
mkdir -p "$DEST"
rsync -a "$SRC/" "$DEST/"
git -C "$DEST" init -q
git -C "$DEST" add -Af .
git -C "$DEST" -c user.name=stage4 -c user.email=stage4@localhost commit -qm 'apache/hadoop rel/release-3.4.2 (copied from the Misconfiguration repository)'
git -C "$DEST" tag rel/release-3.4.2
echo "copied $SRC -> $DEST ($(git -C "$DEST" describe --tags))"
