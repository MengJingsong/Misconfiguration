#!/usr/bin/env bash
# One-off SSH/git setup for a fresh CloudLab node in the misconfiguration
# project. Idempotent — safe to re-run. See /proj/misconfiguration-PG0/README.md "Setup checklist".
#
# usage: setup-node.sh [--peers "HOST ..."] [--no-github] [--no-verify] [-h]
#   --peers     also set up passwordless SSH between this node and each HOST
#               (e.g. "pc57 pc50", "node0 node1", or full names). A short pcNN
#               name expands to pcNN.cloudlab.umass.edu. Uses the shared deploy
#               key (also authorized on this node) and trusts the peers' host
#               keys; peers are expected to already authorize that key.
#   --no-github skip the GitHub steps (1-4)
#   --no-verify skip the connection tests
#   --timezone Z  system time zone to set (default America/New_York, US Eastern:
#               EST, EDT in summer; "EST" is a fixed UTC-5); --no-timezone skips it
#   --no-claude skip installing Claude Code (installed via claude.ai/install.sh)
#   --no-codex  skip installing the OpenAI Codex CLI (chatgpt.com/codex/install.sh)
set -euo pipefail

WORKSPACE=/proj/misconfiguration-PG0
REPOS=("$WORKSPACE/git-repos/Misconfiguration" "$WORKSPACE/git-repos/cassandra-src")
DEPLOY_KEY="$WORKSPACE/.ssh/id_ed25519"          # GitHub deploy key, also the node-to-node key (shared mount)
DOMAIN=cloudlab.umass.edu
SSH_DIR="$HOME/.ssh"
CONFIG="$SSH_DIR/config"

PEERS=()
TIMEZONE=America/New_York
DO_GITHUB=1
DO_VERIFY=1
DO_CLAUDE=1
DO_CODEX=1
while [ $# -gt 0 ]; do
    case "$1" in
        --peers)     read -r -a PEERS <<< "${2:?--peers needs a host list}"; shift 2 ;;
        --peers=*)   read -r -a PEERS <<< "${1#*=}"; shift ;;
        --no-github) DO_GITHUB=0; shift ;;
        --no-verify) DO_VERIFY=0; shift ;;
        --no-claude) DO_CLAUDE=0; shift ;;
        --no-codex)  DO_CODEX=0; shift ;;
        --timezone)  TIMEZONE=${2:?--timezone needs a zone}; shift 2 ;;
        --timezone=*) TIMEZONE=${1#*=}; shift ;;
        --no-timezone) TIMEZONE=""; shift ;;
        -h|--help)   awk 'NR > 1 && !/^#/ {exit} NR > 1 {sub(/^# ?/, ""); print}' "$0"; exit 0 ;;
        *)           echo "unknown argument: $1 (see -h)" >&2; exit 2 ;;
    esac
done

# ---------------------------------------------------------------- helpers

ensure_ssh_dir() {
    mkdir -p "$SSH_DIR"; chmod 700 "$SSH_DIR"
    touch "$SSH_DIR/known_hosts" "$CONFIG" "$SSH_DIR/authorized_keys"
    chmod 600 "$CONFIG" "$SSH_DIR/authorized_keys"
}

# set_block NAME CONTENT: write CONTENT into ~/.ssh/config between markers,
# replacing an earlier block of the same NAME (so re-runs update, not append)
set_block() {
    local name=$1 content=$2 tmp
    tmp=$(mktemp)
    awk -v b="# >>> setup-node: $name" -v e="# <<< setup-node: $name" '
        $0 == b {skip=1; next} $0 == e {skip=0; next} !skip' "$CONFIG" > "$tmp"
    { cat "$tmp"; printf '%s\n%s\n%s\n' "# >>> setup-node: $name" "$content" "# <<< setup-node: $name"; } > "$CONFIG"
    rm -f "$tmp"; chmod 600 "$CONFIG"
}

# trust_host SCAN NAME...: scan SCAN's host keys and store them under each NAME,
# replacing old entries (CloudLab reuses names across experiments, so a changed
# key is expected and must not block)
trust_host() {
    local scan=$1 keys h; shift
    keys=$(ssh-keyscan -T 5 -t ed25519,rsa "$scan" 2>/dev/null | grep -v '^#') || true
    [ -n "$keys" ] || return 1
    for h in "$@"; do
        ssh-keygen -R "$h" >/dev/null 2>&1 || true
        sed "s/^[^ ]*/$h/" <<< "$keys" >> "$SSH_DIR/known_hosts"
    done
    ssh-keygen -H -f "$SSH_DIR/known_hosts" >/dev/null 2>&1 || true
    rm -f "$SSH_DIR/known_hosts.old"
}

# the names and addresses this node answers to (to skip itself in the peer list)
self_names() {
    local ip
    hostname; hostname -f 2>/dev/null || true; hostname -s
    for ip in $(hostname -I 2>/dev/null); do
        echo "$ip"
        getent hosts "$ip" | awk '{for (i = 2; i <= NF; i++) print $i}'
    done
}

ensure_ssh_dir

# ---------------------------------------------------------------- time zone (step 0)

if [ -n "$TIMEZONE" ]; then
    echo "0. Setting the system time zone to $TIMEZONE..."
    current=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo unknown)
    if [ "$current" = "$TIMEZONE" ]; then
        echo "   already $TIMEZONE"
    elif [ ! -e "/usr/share/zoneinfo/$TIMEZONE" ]; then
        echo "   WARNING: unknown time zone $TIMEZONE (see timedatectl list-timezones), left at $current" >&2
    elif sudo -n timedatectl set-timezone "$TIMEZONE" 2>/dev/null; then
        echo "   changed from $current: $(date '+%F %T %Z')"
    else
        echo "   WARNING: could not set the time zone (needs passwordless sudo), left at $current" >&2
    fi
    [ -z "${TZ:-}" ] || echo "   note: \$TZ=$TZ is set in this shell and overrides the system zone" >&2
    # a running Cassandra node or JVM keeps the zone it started with; restart it to pick this up
fi

# ---------------------------------------------------------------- GitHub (steps 1-4)

if [ "$DO_GITHUB" = 1 ]; then
    echo "1. Trusting shared repo directories with git..."
    for r in "${REPOS[@]}"; do
        if git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$r"; then
            echo "   already trusted: $r"
        else
            git config --global --add safe.directory "$r"; echo "   added: $r"
        fi
    done

    echo "2. Trusting GitHub's host key..."
    if ssh-keygen -F github.com >/dev/null 2>&1; then
        echo "   already trusted"
    elif trust_host github.com github.com; then
        echo "   added github.com to known_hosts"
    else
        echo "   WARNING: could not scan github.com" >&2
    fi

    echo "3. Pointing git at the shared deploy key..."
    if grep -q "IdentityFile $DEPLOY_KEY" "$CONFIG" && ! grep -q "^# >>> setup-node: github" "$CONFIG" \
       && grep -q "^Host github.com" "$CONFIG"; then
        echo "   already configured (hand-written entry kept)"
    else
        set_block github "Host github.com
    IdentityFile $DEPLOY_KEY
    IdentitiesOnly yes"
        echo "   github.com entry in ~/.ssh/config up to date"
    fi

    if [ "$DO_VERIFY" = 1 ]; then
        echo "4. Verifying GitHub auth..."
        out=$(ssh -o BatchMode=yes -o ConnectTimeout=10 -T git@github.com 2>&1) || true
        if [[ $out == *"successfully authenticated"* ]]; then
            echo "   $out"
        else
            echo "   WARNING: could not confirm GitHub auth: $out" >&2
        fi
    fi
fi

# ---------------------------------------------------------------- peers (step 5)

if [ ${#PEERS[@]} -gt 0 ]; then
    echo "5. Node-to-node SSH with: ${PEERS[*]}"
    if [ ! -f "$DEPLOY_KEY" ]; then
        echo "   ERROR: $DEPLOY_KEY not found (is the shared mount available?)" >&2; exit 1
    fi
    pub=$(cat "$DEPLOY_KEY.pub" 2>/dev/null || ssh-keygen -y -f "$DEPLOY_KEY")
    if grep -qxF "$pub" "$SSH_DIR/authorized_keys"; then
        echo "   deploy key already authorized on this node"
    else
        echo "$pub" >> "$SSH_DIR/authorized_keys"; echo "   authorized the deploy key on this node"
    fi

    mapfile -t SELF < <(self_names | sort -u)
    failed=()
    for p in "${PEERS[@]}"; do
        alias=${p%%.*}
        if [[ $p == *.* ]]; then fqdn=$p
        elif [[ $p =~ ^pc[0-9]+$ ]]; then fqdn="$p.$DOMAIN"
        else fqdn=$p; fi            # e.g. node1, resolved through /etc/hosts
        addrs=$(getent hosts "$fqdn" | awk '{print $1}' | sort -u) || true
        if [ -z "$addrs" ]; then
            echo "   $p: cannot resolve $fqdn, skipped" >&2; failed+=("$p"); continue
        fi
        if printf '%s\n' "${SELF[@]}" | grep -qxF -e "$p" -e "$fqdn" $(printf -- '-e %s ' $addrs); then
            echo "   $p: this node, skipped"; continue
        fi
        # shellcheck disable=SC2086
        if trust_host "$fqdn" $(printf '%s\n' "$alias" "$fqdn" $addrs | sort -u); then
            echo "   $p: host key trusted"
        else
            echo "   $p: no SSH answer from $fqdn (port 22), skipped" >&2; failed+=("$p"); continue
        fi
        set_block "peer $alias" "Host $alias $fqdn
    HostName $fqdn
    User $USER
    IdentityFile $DEPLOY_KEY
    IdentitiesOnly yes"
        if [ "$DO_VERIFY" = 1 ]; then
            # test the deploy key alone, ignoring any other ~/.ssh/config entry for this host
            if ssh -F /dev/null -o BatchMode=yes -o ConnectTimeout=10 -o IdentitiesOnly=yes -i "$DEPLOY_KEY" \
                   -o UserKnownHostsFile="$SSH_DIR/known_hosts" -o StrictHostKeyChecking=yes "$USER@$fqdn" true 2>/dev/null; then
                echo "   $p: ssh $alias OK (deploy key)"
            else
                echo "   $p: ssh $alias failed — is the deploy key in $p's ~/.ssh/authorized_keys?" >&2
                failed+=("$p")
            fi
        fi
    done
    [ ${#failed[@]} -eq 0 ] || echo "   peers not ready: ${failed[*]}" >&2
fi

# ---------------------------------------------------------------- Claude Code (step 6)

if [ "$DO_CLAUDE" = 1 ]; then
    echo "6. Installing Claude Code..."
    # the installer puts the binary in ~/.local/bin
    export PATH="$HOME/.local/bin:$PATH"
    if command -v claude >/dev/null 2>&1; then
        echo "   already installed: $(claude --version 2>/dev/null || echo claude)"
    elif curl -fsSL https://claude.ai/install.sh | bash; then
        echo "   installed: $(claude --version 2>/dev/null || echo 'claude (open a new shell if not on PATH)')"
    else
        echo "   WARNING: Claude Code install failed" >&2
    fi
fi

# ---------------------------------------------------------------- Codex CLI (step 7)

if [ "$DO_CODEX" = 1 ]; then
    echo "7. Installing the Codex CLI..."
    # OpenAI's standalone installer: package in ~/.codex/packages/standalone, symlink
    # ~/.local/bin/codex (no Node.js needed). A bare binary (what an earlier version of
    # this script installed) is replaced: `codex remote-control` / the app-server
    # daemon refuse to run without the package ("no complete local package").
    export PATH="$HOME/.local/bin:$PATH"
    if [ -L "$HOME/.local/bin/codex" ] && [ -d "$HOME/.codex/packages/standalone" ] \
       && command -v codex >/dev/null 2>&1; then
        echo "   already installed: $(codex --version 2>/dev/null || echo codex)"
    else
        [ ! -f "$HOME/.local/bin/codex" ] || [ -L "$HOME/.local/bin/codex" ] \
            || echo "   replacing the bare binary ~/.local/bin/codex with the packaged install"
        if curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh; then
            echo "   installed: $(codex --version 2>/dev/null || echo 'codex (open a new shell if not on PATH)')"
            echo "   sign in once with: codex login"
        else
            echo "   WARNING: Codex CLI install failed" >&2
        fi
    fi
fi

# ---------------------------------------------------------------- PATH for the installed CLIs

if [ "$DO_CLAUDE" = 1 ] || [ "$DO_CODEX" = 1 ]; then
    # make ~/.local/bin permanent on PATH for new shells (once, not on every re-run)
    PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
    if grep -qxF "$PATH_LINE" "$HOME/.bashrc" 2>/dev/null; then
        echo "   ~/.bashrc already adds ~/.local/bin to PATH"
    else
        echo "$PATH_LINE" >> "$HOME/.bashrc"
        echo "   added ~/.local/bin to PATH in ~/.bashrc"
    fi
fi

echo "Done."
