#!/bin/bash
# RPL Tree topology setup via TX power control
#
# 15 nodes → 3-level tree:
#   Level 0 (root)  : Node[0]  — border router  (TX: default +3 dBm)
#   Level 1         : Node[1..4]  — 4 nodes       (TX: 0 dBm)
#   Level 2         : Node[5..9]  — 5 nodes       (TX: -10 dBm)
#   Level 3 (leaf)  : Node[10..14] — 5 nodes      (TX: -17 dBm)
#
# Lower TX power → shorter range → forced multi-hop
# RPL builds DODAG automatically from border router outward
set -euo pipefail

NODE_FILE=/tmp/iotlab_nodes
[[ -f "$NODE_FILE" ]] || { echo "ERROR: run 01_submit.sh first"; exit 1; }

mapfile -t NODES < "$NODE_FILE"

set_txpower() {
    local node=$1
    local power=$2   # dBm, e.g.: 3, 0, -10, -17
    echo "[TOPO] $node → TX power ${power} dBm"
    # Command goes to M3 RIOT shell via serial
    ssh "root@node-${node}" \
        "echo 'ifconfig 7 set txpower ${power}' > /dev/ttyA8_M3" 2>/dev/null || true
}

echo "[TOPO] Configuring tree topology (TX power based)"

# Level 0: Border router — keep default (+3 dBm), skipping
echo "[TOPO] ${NODES[0]} = root (default TX power)"

# Level 1: can reach root
for i in 1 2 3 4; do
    set_txpower "${NODES[$i]}" 0
done

# Level 2: can reach Level-1 but not root
for i in 5 6 7 8 9; do
    set_txpower "${NODES[$i]}" -10
done

# Level 3: leaves, can only reach Level-2
for i in 10 11 12 13 14; do
    set_txpower "${NODES[$i]}" -17
done

echo "[TOPO] Waiting 15s for RPL to rebuild DODAG..."
sleep 15

# Verify topology by checking RPL parents on a few nodes
echo "[TOPO] Checking RPL routing table on sample nodes..."
for node in "${NODES[5]}" "${NODES[10]}"; do
    echo "--- RPL on $node ---"
    ssh "root@node-${node}" \
        "echo 'rpl' > /dev/ttyA8_M3; sleep 1; cat /dev/ttyA8_M3" 2>/dev/null || true
done

echo "[TOPO] Tree topology setup complete."
echo "[TOPO] Level 0 (root): ${NODES[0]}"
echo "[TOPO] Level 1      : ${NODES[*]:1:4}"
echo "[TOPO] Level 2      : ${NODES[*]:5:5}"
echo "[TOPO] Level 3      : ${NODES[*]:10:5}"
