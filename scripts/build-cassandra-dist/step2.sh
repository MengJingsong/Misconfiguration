#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <seeds> <node_ip>"
    echo "Example: $0 \"192.168.1.10:7000,192.168.1.11:7000\" \"192.168.1.12\""
    exit 1
fi

SEEDS="$1"
NODE_IP="$2"
YAML_FILE="conf/cassandra.yaml"

if [[ ! -f "$YAML_FILE" ]]; then
    echo "Error: $YAML_FILE not found"
    exit 1
fi

cp "$YAML_FILE" "${YAML_FILE}.bak"

sed -i \
    -e "s|^\([[:space:]]*-[[:space:]]*seeds:[[:space:]]*\)\"[^\"]*\"|\1\"$SEEDS\"|" \
    -e "s|^listen_address:.*|listen_address: $NODE_IP|" \
    -e "s|^# broadcast_address:.*|broadcast_address: $NODE_IP|" \
    -e "s|^rpc_address:.*|rpc_address: 0.0.0.0|" \
    -e "s|^# broadcast_rpc_address:.*|broadcast_rpc_address: $NODE_IP|" \
    "$YAML_FILE"

echo "Updated $YAML_FILE"
echo "  seeds = $SEEDS"
echo "  listen_address = $NODE_IP"
echo "  broadcast_address = $NODE_IP"
echo "  rpc_address = 0.0.0.0"
echo "  broadcast_rpc_address = $NODE_IP"
echo "Backup saved to ${YAML_FILE}.bak"
