#!/bin/bash

set -euo pipefail

sudo apt-get update
sudo apt-get install -y openjdk-8-jdk
sudo apt-get install maven

cd /mydata
sudo chmod 777 .

if [[ ! -d "hadoop-3.4.2" ]]; then
        tar xvf /proj/misconfiguration-PG0/tarfiles/hadoop-3.4.2.tar.gz -C /mydata
fi

append_to_bashrc_if_absent() {
  local file="$HOME/.bashrc"
  local line="$1"

  # Ensure file exists
  touch "$file"

  # If the exact line isn't present (-x: match whole line, -F: fixed string), append it
  if ! grep -qxF -- "$line" "$file" 2>/dev/null; then
    echo "$line" >> "$file"
  fi
}

append_to_bashrc_if_absent 'export HADOOP_HOME=/mydata/hadoop-3.4.2'
append_to_bashrc_if_absent 'export YARN_HOME=$HADOOP_HOME'
append_to_bashrc_if_absent 'export HADOOP_COMMON_HOME=$HADOOP_HOME'
append_to_bashrc_if_absent 'export HADOOP_HDFS_HOME=$HADOOP_HOME'
append_to_bashrc_if_absent 'export HADOOP_YARN_HOME=$HADOOP_HOME'
append_to_bashrc_if_absent 'export HADOOP_MAPRED_HOME=$HADOOP_HOME'
append_to_bashrc_if_absent 'export HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop'
append_to_bashrc_if_absent 'export YARN_CONF_DIR=$HADOOP_HOME/etc/hadoop'
append_to_bashrc_if_absent 'export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64'
append_to_bashrc_if_absent 'export PATH=$PATH:$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$JAVA_HOME/bin'

source /users/jason92/.bashrc

mv -b /proj/misconfiguration-PG0/scripts/build-hadoop-dist/core-site.xml /mydata/hadoop-3.4.2/etc/hadoop
mv -b /proj/misconfiguration-PG0/scripts/build-hadoop-dist/hdfs-site.xml /mydata/hadoop-3.4.2/etc/hadoop
mv -b /proj/misconfiguration-PG0/scripts/build-hadoop-dist/yarn-site.xml /mydata/hadoop-3.4.2/etc/hadoop
mv -b /proj/misconfiguration-PG0/scripts/build-hadoop-dist/hadoop-env.sh /mydata/hadoop-3.4.2/etc/hadoop
