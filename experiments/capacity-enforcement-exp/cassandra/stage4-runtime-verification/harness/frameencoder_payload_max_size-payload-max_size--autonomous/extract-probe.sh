#!/bin/bash
# Defect fix D1 (2026-11-25): the unit-test JVM routes System.out through a logger (SubstituteLogger), one log line per
# print() fragment, and nothing reaches the JUnit XML. Rebuild the PROBE lines from the ant testsome log.
# Usage: extract-probe.sh <testsome.log>
grep -F 'SubstituteLogger.java' "$1" | sed 's/.*SubstituteLogger\.java:[0-9]* - //' | tr -d '\n' | sed 's/PROBE /\nPROBE /g' | grep '^PROBE'
echo
