#!/bin/bash
# Applies the relaxed-guardrail config from ../oom-exp/updated-conf/ needed
# by oom-exp/exp1 (tombstone flood), scoped to exactly the guardrails
# documented in oom-exp/exp1/README.md's "Guardrails this experiment relies
# on being relaxed" table -- NOT a wholesale copy of updated-conf, which
# also carries a hardcoded single-node address and unrelated tuning left
# over from an earlier experiment.
#
# Run on each node after step2.sh (node addressing must already be in
# place). Idempotent -- re-running is safe, sed patches match on the
# default/original value so a second run is a no-op diff.
set -euo pipefail

CASSANDRA_HOME="/mydata/apache-cassandra-5.0.7"
YAML_FILE="$CASSANDRA_HOME/conf/cassandra.yaml"
ENV_FILE="$CASSANDRA_HOME/conf/cassandra-env.sh"

for f in "$YAML_FILE" "$ENV_FILE"; do
    if [[ ! -f "$f" ]]; then
        echo "Error: $f not found" >&2
        exit 1
    fi
done

cp "$YAML_FILE" "${YAML_FILE}.bak"
cp "$ENV_FILE" "${ENV_FILE}.bak"

# --- cassandra.yaml ---

sed -i \
    -e "s|^tombstone_warn_threshold:.*|tombstone_warn_threshold: 2147483647|" \
    -e "s|^tombstone_failure_threshold:.*|tombstone_failure_threshold: 2147483647|" \
    -e "s|^read_request_timeout:.*|read_request_timeout: 60000ms|" \
    -e "s|^range_request_timeout:.*|range_request_timeout: 120000ms|" \
    -e "s|^request_timeout:.*|request_timeout: 120000ms|" \
    "$YAML_FILE"

if ! grep -q "^autocompaction_on_startup_enabled:" "$YAML_FILE"; then
    echo "autocompaction_on_startup_enabled: false" >> "$YAML_FILE"
else
    sed -i "s|^autocompaction_on_startup_enabled:.*|autocompaction_on_startup_enabled: false|" "$YAML_FILE"
fi

# --- cassandra-env.sh ---

# MAX_HEAP_SIZE is commented out by default (left to calculate_heap_sizes());
# uncomment and pin it to 512M regardless of what value (if any) follows the
# commented-out default on this node.
sed -i -E "s|^#?MAX_HEAP_SIZE=.*|MAX_HEAP_SIZE=\"512M\"|" "$ENV_FILE"

# Don't let the JVM kill -9 itself on OOM before it can dump a heap
# histogram; capture the histogram instead.
sed -i \
    -e 's|^JVM_ON_OUT_OF_MEMORY_ERROR_OPT="-XX:OnOutOfMemoryError=kill -9 %p"|# JVM_ON_OUT_OF_MEMORY_ERROR_OPT="-XX:OnOutOfMemoryError=kill -9 %p"\nJVM_ON_OUT_OF_MEMORY_ERROR_OPT=""|' \
    "$ENV_FILE"

if ! grep -q "printHeapHistogramOnOutOfMemoryError=true" "$ENV_FILE"; then
    echo 'JVM_OPTS="$JVM_OPTS -Dcassandra.printHeapHistogramOnOutOfMemoryError=true"' >> "$ENV_FILE"
fi

echo "Applied relaxed guardrails to $YAML_FILE and $ENV_FILE (backups: *.bak)"
echo "  tombstone_warn_threshold / tombstone_failure_threshold = 2147483647"
echo "  read/range/request_timeout = 60000ms / 120000ms / 120000ms"
echo "  autocompaction_on_startup_enabled = false"
echo "  MAX_HEAP_SIZE = 512M"
echo "  JVM_ON_OUT_OF_MEMORY_ERROR_OPT disabled, printHeapHistogramOnOutOfMemoryError=true"
echo "Restart Cassandra on this node for the new config to take effect."
