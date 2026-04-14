#!/bin/bash
set -euo pipefail

if ! compgen -G "$HOME/.ssh/*.pub" > /dev/null; then
        echo "no ssh key, generate one"
        ssh-keygen -t rsa -P '' -f ~/.ssh/id_rsa
        cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
        chmod 0600 ~/.ssh/authorized_keys
fi

PUBKEY_CONTENT="$(cat ~/.ssh/id_rsa.pub)"
PUBKEYS_PATH="/proj/misconfiguration-PG0/scripts/public_keys"
AUTH_FILE="$HOME/.ssh/authorized_keys"

mkdir -p "$(dirname -- "$PUBKEYS_PATH")"
touch "$PUBKEYS_PATH"
if ! grep -qxF -- "$PUBKEY_CONTENT" "$PUBKEYS_PATH"; then
        echo "$PUBKEY_CONTENT" >> "$PUBKEYS_PATH"
fi

while IFS= read -r line; do
        if ! grep -qxF -- "$line" "$AUTH_FILE"; then
                echo >> "$AUTH_FILE"
                echo "$line" >> "$AUTH_FILE"
        fi
done < "$PUBKEYS_PATH"
