#!/bin/bash
# Phase 2: Run CoAP experiment
# - Node[0] M3 → CoAP server
# - Node[1..13] M3 → CoAP clients
set -euo pipefail

SITE=saclay
PROJDIR=$(cd "$(dirname "$0")/.." && pwd)
NODE_FILE=/tmp/iotlab_nodes
RESULTS_DIR="$PROJDIR/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$RESULTS_DIR/coap_raw_${TIMESTAMP}.log"

mkdir -p "$RESULTS_DIR"
mapfile -t NODES < "$NODE_FILE"
SERVER_NODE=${NODES[0]}

# Get M3 IPv6 address of server node (link-local won't work across hops,
# use the RPL-assigned global addr)
echo "[COAP] Getting server M3 global IPv6 ..."
SERVER_M3_ADDR=$(ssh "root@node-${SERVER_NODE}" \
    "echo 'ifconfig' > /dev/ttyA8_M3; sleep 1; cat /dev/ttyA8_M3" | \
    grep -oP '(?<=inet6 addr: )2[0-9a-f:]+(?= )' | head -1)

echo "[COAP] Server: $SERVER_NODE  M3 addr: $SERVER_M3_ADDR"
echo "$SERVER_M3_ADDR" > /tmp/coap_server_addr

# 1) Serial monitors
echo "[COAP] Opening serial monitors → $LOG_FILE"
for node in "${NODES[@]:0:14}"; do
    ssh "root@node-${node}" \
        "miniterm.py /dev/ttyA8_M3 500000 -e 2>/dev/null" >> "$LOG_FILE" &
done

sleep 2

# 2) Set server role on node[0]
echo "[COAP] Setting server role on $SERVER_NODE ..."
ssh "root@node-${SERVER_NODE}" \
    "echo 'role server' > /dev/ttyA8_M3"
sleep 2

# 3) Set client role on all other nodes
echo "[COAP] Setting client role on remaining nodes ..."
for node in "${NODES[@]:1:13}"; do
    ssh "root@node-${node}" \
        "echo 'role client ${SERVER_M3_ADDR}' > /dev/ttyA8_M3" &
done
sleep 5

# 4) Run
echo "[COAP] Starting experiment on clients ..."
for node in "${NODES[@]:1:13}"; do
    ssh "root@node-${node}" \
        "echo 'run' > /dev/ttyA8_M3" &
done

echo "[COAP] Collecting for 150s ..."
sleep 150

kill %% 2>/dev/null || true
wait 2>/dev/null || true

echo "[COAP] Raw log: $LOG_FILE"
grep "^CSV,COAP" "$LOG_FILE" > "$RESULTS_DIR/coap_csv_${TIMESTAMP}.csv" || true
grep "^SUMMARY,COAP" "$LOG_FILE"
echo "[COAP] Done."
