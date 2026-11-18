#!/usr/bin/env bash
# R7: alias IPs for C2..C8 on ms0640 (enp1s0d1). alias.sh up | down | show
case $1 in
  up) for x in $(seq 71 77); do
        if ping -c1 -W1 10.10.1.$x >/dev/null 2>&1; then echo "10.10.1.$x answers, not free"; exit 1; fi
      done
      for x in $(seq 71 77); do ssh ms0640 "sudo -n ip addr add 10.10.1.$x/24 dev enp1s0d1"; done ;;
  down) for x in $(seq 71 77); do ssh ms0640 "sudo -n ip addr del 10.10.1.$x/24 dev enp1s0d1" 2>/dev/null; done ;;
esac
ssh ms0640 "ip -4 addr show enp1s0d1 | grep inet"
