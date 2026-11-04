#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT_GUESS="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=/dev/null
source "$REPO_ROOT_GUESS/config/environment.sh"

CASSANDRA_VERSION="$CASSANDRA_VERSION"
TARBALL="apache-cassandra-${CASSANDRA_VERSION}-bin.tar.gz"

sudo apt-get update
sudo apt-get install -y openjdk-17-jdk
sudo apt-get install -y ant

mkdir -p "$PROJ/tarfiles"
cd "$PROJ/tarfiles"

if [[ ! -f "$TARBALL" ]]; then
	wget "https://archive.apache.org/dist/cassandra/${CASSANDRA_VERSION}/${TARBALL}"
fi

cd /mydata
sudo chmod 777 .

if [[ ! -d "apache-cassandra-${CASSANDRA_VERSION}" ]]; then
	tar xvf "$PROJ/tarfiles/$TARBALL" -C /mydata
fi

append_to_bashrc_if_absent() {
  local file="$HOME/.bashrc"
  local line="$1"
  touch "$file"
  if ! grep -qxF -- "$line" "$file" 2>/dev/null; then
    echo "$line" >> "$file"
  fi
}

append_to_bashrc_if_absent 'export JAVA_HOME_17=/usr/lib/jvm/java-17-openjdk-amd64'
append_to_bashrc_if_absent "export CASSANDRA_HOME=$MYDATA_CASSANDRA_HOME"
append_to_bashrc_if_absent 'export PATH=$CASSANDRA_HOME/bin:$CASSANDRA_HOME/tools/bin:$JAVA_HOME_17/bin:$PATH'
append_to_bashrc_if_absent 'export CASSANDRA_USE_JDK17=true'

source "$HOME/.bashrc"

sudo ufw allow 7000
sudo ufw allow 9042
sudo ufw allow 7199
