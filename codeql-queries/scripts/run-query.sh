#!/usr/bin/env bash
# Run one or more CodeQL queries against a target database.
#
# Usage:
#   ./run-query.sh <cassandra|hadoop> <query-or-dir-path> [output-name]
#
# Examples:
#   ./run-query.sh cassandra cassandra/queries/if-check-exp/Example.ql
#   ./run-query.sh hadoop hadoop/queries
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUERIES_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CODEQL_BIN="${CODEQL_BIN:-codeql}"
DB_ROOT="${CODEQL_DB_ROOT:-/proj/misconfiguration-PG0/codeql-dbs}"

target="${1:?usage: run-query.sh <cassandra|hadoop> <query-path> [output-name]}"
query_path="${2:?usage: run-query.sh <cassandra|hadoop> <query-path> [output-name]}"
out_name="${3:-$(basename "$query_path" .ql)}"

case "$target" in
  cassandra) db="$DB_ROOT/cassandra-db" ;;
  hadoop)    db="$DB_ROOT/hadoop-db" ;;
  *) echo "unknown target: $target (expected cassandra|hadoop)" >&2; exit 1 ;;
esac

if [[ ! -d "$db" ]]; then
  echo "database not found: $db" >&2
  exit 1
fi

mkdir -p "$QUERIES_ROOT/results/$target"
out_file="$QUERIES_ROOT/results/$target/${out_name}.sarif"

echo "Running $query_path against $db"
"$CODEQL_BIN" database analyze "$db" "$QUERIES_ROOT/$query_path" \
  --format=sarif-latest \
  --output="$out_file"

echo "Results written to $out_file"
