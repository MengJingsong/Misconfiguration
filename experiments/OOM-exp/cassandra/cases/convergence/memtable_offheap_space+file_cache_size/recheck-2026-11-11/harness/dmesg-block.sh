#!/usr/bin/env bash
# Save the kernel OOM block (invoked oom-killer .. Killed process) for an arm's scope unit, plus the clock offset.
d=$1; U=$(grep -o 'oom-r1-[0-9]*' "$d/summary.txt" | head -1)
sudo -n dmesg | awk -v u="$U" '/invoked oom-killer/{buf=""; on=1} on{buf=buf $0 "\n"} /Killed process/ && on{ if (index(buf,u)) printf "%s", buf; on=0 }' > "$d/dmesg-block.txt"
echo "clock: epoch $(date +%s.%N) uptime $(cut -d' ' -f1 /proc/uptime) (dmesg stamps are sched_clock; may drift a few s from wall time)" >> "$d/dmesg-block.txt"
wc -l < "$d/dmesg-block.txt"
