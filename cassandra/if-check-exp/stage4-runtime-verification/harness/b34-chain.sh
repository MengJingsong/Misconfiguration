#!/usr/bin/env bash
# runs, one after another on the run node, the cluster tiers of the three cases (shared helper of this batch; each case's chain.sh is its own)
B=$(cd "$(dirname "$0")" && pwd)
$B/max_keys_sparse-addinternal-keys--autonomous/chain.sh
$B/native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous/chain.sh
$B/native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous/chain.sh
