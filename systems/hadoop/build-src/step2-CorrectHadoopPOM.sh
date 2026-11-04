#!/usr/bin/env bash
set -euo pipefail

# Usage: build-hadoop.sh [path-to-pom]
# Default path targets the requested pom.xml in the environment
POM_PATH="${1:-/mydata/hadoop-3.4.2-src/hadoop-project/pom.xml}"
NODE_VER="v20.12.2"
YARN_VER="v1.22.22"

if [ ! -f "$POM_PATH" ]; then
  echo "Error: pom.xml not found at $POM_PATH" >&2
  exit 1
fi

BACKUP="$POM_PATH.$(date +%Y%m%d%H%M%S).bak"
cp -- "$POM_PATH" "$BACKUP"
echo "Backup created: $BACKUP"

# Try a simple in-place sed replacement first (works for single-line tags)
sed -E -i "s|<nodejs.version>[^<]*</nodejs.version>|<nodejs.version>${NODE_VER}</nodejs.version>|g" "$POM_PATH" || true
sed -E -i "s|<yarnpkg.version>[^<]*</yarnpkg.version>|<yarnpkg.version>${YARN_VER}</yarnpkg.version>|g" "$POM_PATH" || true

# If tags span multiple lines or sed didn't catch them, use perl to replace across newlines
if ! grep -q "<nodejs.version>${NODE_VER}</nodejs.version>" "$POM_PATH" 2>/dev/null; then
  if command -v perl >/dev/null 2>&1; then
    perl -0777 -pe "s#<nodejs.version>.*?</nodejs.version>#<nodejs.version>${NODE_VER}</nodejs.version>#gs" -i "$POM_PATH"
  fi
fi

if ! grep -q "<yarnpkg.version>${YARN_VER}</yarnpkg.version>" "$POM_PATH" 2>/dev/null; then
  if command -v perl >/dev/null 2>&1; then
    perl -0777 -pe "s#<yarnpkg.version>.*?</yarnpkg.version>#<yarnpkg.version>${YARN_VER}</yarnpkg.version>#gs" -i "$POM_PATH"
  fi
fi

echo "Updated $POM_PATH"
echo "Current values:"
grep -nE "<(nodejs|yarnpkg)\.version>.*</(nodejs|yarnpkg)\.version>" "$POM_PATH" || true

echo "Done. Original backup saved to: $BACKUP"
