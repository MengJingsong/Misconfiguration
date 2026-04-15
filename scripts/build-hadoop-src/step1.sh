#!/bin/bash

set -euo pipefail

sudo apt-get update
sudo apt-get install -y openjdk-8-jdk
sudo apt-get install maven

if [ -d "/proj/misconfiguration-PG0" ]; then
        PROJ="/proj/misconfiguration-PG0"
else
        PROJ="/proj/Misconfiguration"
fi

cd $PROJ/tarfiles

if [[ ! -d "hadoop-3.4.2-src.tar.gz" ]]; then
        wget https://dlcdn.apache.org/hadoop/common/hadoop-3.4.2/hadoop-3.4.2-src.tar.gz
fi

cd /mydata
sudo chmod 777 .

if [[ ! -d "hadoop-3.4.2-src" ]]; then
        tar xvf $PROJ/tarfiles/hadoop-3.4.2-src.tar.gz -C /mydata
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

# cd /mydata/hadoop-3.4.2/etc/hadoop
# grep -o -E 'node[0-9]+$' /etc/hosts > workers
# grep -o -E 'node[0-9]+$' /etc/hosts > slaves

PROTOBUF_URL=https://github.com/google/protobuf/releases/download/v2.5.0/protobuf-2.5.0.tar.gz
if [[ ! -d "protobuf-2.5.0" ]]; then
	wget $PROTOBUF_URL
	tar xvf protobuf-2.5.0.tar.gz
	cd protobuf-2.5.0
	sudo apt-get install autoconf libtool
	./autogen.sh
	./configure
	make -j
	sudo make install
	sudo ldconfig
	protoc --version
fi

