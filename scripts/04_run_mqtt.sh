#!/bin/bash
# Phase 1: Run MQTT-SN experiment
# - Start RSMB broker on border router A8
# - Connect all M3 nodes to broker
# - Trigger 'run' command on each node
# - Collect serial output to log file
set -euo pipefail

SITE=saclay
PROJDIR=$(cd "$(dirname "$0")/.." && pwd)
NODE_FILE=/tmp/iotlab_nodes
RESULTS_DIR="$PROJDIR/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$RESULTS_DIR/mqtt_raw_${TIMESTAMP}.log"

mkdir -p "$RESULTS_DIR"
mapfile -t NODES < "$NODE_FILE"
BR_NODE=${NODES[0]}
BR_ADDR=$(cat /tmp/br_addr)

echo "[MQTT] Border router: $BR_NODE  IPv6: $BR_ADDR"

# 1) Start RSMB on A8 Linux side
echo "[MQTT] Starting RSMB broker on $BR_NODE ..."
ssh "root@node-${BR_NODE}" "
    pkill -f broker_mqtts 2>/dev/null || true
    cp $PROJDIR/broker/rsmb.conf /tmp/rsmb.conf
    nohup broker_mqtts /tmp/rsmb.conf > /tmp/rsmb_out.log 2>&1 &
    sleep 2
    echo 'RSMB PID:' \$(pgrep broker_mqtts)
"

# 2) Set up serial monitor (collect all M3 output)
echo "[MQTT] Opening serial monitors → $LOG_FILE"
for node in "${NODES[@]:0:14}"; do
    num=${node#a8-}
    ssh "root@node-${node}" \
        "miniterm.py /dev/ttyA8_M3 500000 -e 2>/dev/null" >> "$LOG_FILE" &
done

# 3) Connect each M3 node to broker via shell command
sleep 3
echo "[MQTT] Connecting nodes to broker..."
for node in "${NODES[@]:0:14}"; do
    ssh "root@node-${node}" \
        "echo 'con ${BR_ADDR}' > /dev/ttyA8_M3" &
done
sleep 5

# 4) Trigger experiment on each node
echo "[MQTT] Starting experiment on all nodes..."
for node in "${NODES[@]:0:14}"; do
    ssh "root@node-${node}" \
        "echo 'run' > /dev/ttyA8_M3" &
done

# NUM_MESSAGES * SEND_INTERVAL + margin = 200*0.5s + 30s = 130s
echo "[MQTT] Collecting for 150s ..."
sleep 150

# 5) Kill monitors
kill %% 2>/dev/null || true
wait 2>/dev/null || true

echo "[MQTT] Raw log: $LOG_FILE"
echo "[MQTT] Parsing CSV lines..."
grep "^CSV,MQTTSN" "$LOG_FILE" > "$RESULTS_DIR/mqtt_csv_${TIMESTAMP}.csv" || true
grep "^SUMMARY,MQTTSN" "$LOG_FILE"
echo "[MQTT] Done."
