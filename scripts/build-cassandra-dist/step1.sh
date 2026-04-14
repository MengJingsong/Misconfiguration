#!/bin/bash

set -euo pipefail

sudo apt-get update
sudo apt-get install -y openjdk-17-jdk
sudo apt-get install ant

cd /mydata
sudo chmod 777 .

if [[ ! -d "apache-cassandra-5.0.7" ]]; then
        tar xvf /proj/misconfiguration-PG0/tarfiles/apache-cassandra-5.0.7-bin.tar.gz -C /mydata
fi

append_to_bashrc_if_absent() {
  local file="$HOME/.bashrc"
  local line="$1"

  echo $file

  # Ensure file exists
  touch "$file"

  # If the exact line isn't present (-x: match whole line, -F: fixed string), append it
  if ! grep -qxF -- "$line" "$file" 2>/dev/null; then
    echo "$line" >> "$file"
  fi
}

append_to_bashrc_if_absent 'export JAVA_HOME_17=/usr/lib/jvm/java-17-openjdk-amd64'
append_to_bashrc_if_absent 'export PATH=$JAVA_HOME_17/bin:$PATH'
append_to_bashrc_if_absent 'export CASSANDRA_USE_JDK17=true'

sudo ufw allow 7000
sudo ufw allow 9042
sudo ufw allow 7199
