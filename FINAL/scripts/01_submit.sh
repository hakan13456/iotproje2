#!/bin/bash
# Submit 15-node experiment on FIT IoT-LAB Saclay
# Usage: ./01_submit.sh [duration_minutes]
set -euo pipefail

DURATION=${1:-120}   # minutes
SITE=saclay
ARCHI="a8:at86rf231"
NAME="mqtt_vs_coap_tree"
NUM_NODES=15

echo "[SUBMIT] Submitting $NUM_NODES nodes @ $SITE for ${DURATION} min"

RESULT=$(iotlab-experiment submit \
    -n "$NAME" \
    -d "$DURATION" \
    -l "${NUM_NODES},archi=${ARCHI}+site=${SITE}")

EXP_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "[SUBMIT] Experiment ID: $EXP_ID"
echo "$EXP_ID" > /tmp/iotlab_exp_id

echo "[SUBMIT] Waiting for experiment to start..."
iotlab-experiment wait --id "$EXP_ID" --state Running --timeout 120

echo "[SUBMIT] Getting node list..."
iotlab-experiment get --id "$EXP_ID" -n | \
    python3 -c "
import sys,json
data = json.load(sys.stdin)
nodes = sorted([n.split('.')[0].replace('a8-','') for n in data['items'][0]['network_address']], key=int)
print('Nodes:', ' '.join(['a8-'+n for n in nodes]))
# Write to file
with open('/tmp/iotlab_nodes', 'w') as f:
    f.write('\n'.join(['a8-'+n for n in nodes]))
print('Node list saved to /tmp/iotlab_nodes')
"
