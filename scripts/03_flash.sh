#!/bin/bash
# Flash all nodes:
#   - Node[0]  → border router (A8 Linux side) + mqtt_node (M3 side) for MQTT phase
#   - Node[1..7]  → mqtt_node  (MQTT-SN experiment)
#   - Node[8..14] → coap_node  (CoAP experiment)
#
# Usage: ./03_flash.sh mqtt | coap | both
set -euo pipefail

SITE=saclay
PHASE=${1:-mqtt}
NODE_FILE=/tmp/iotlab_nodes

[[ -f "$NODE_FILE" ]] || { echo "ERROR: run 01_submit.sh first"; exit 1; }

mapfile -t NODES < "$NODE_FILE"
BR_NODE=${NODES[0]}   # border router
BR_NUM=${BR_NODE#a8-}

echo "[FLASH] Border router on $BR_NODE"
# Flash border router ELF to A8 Linux side
ssh "root@node-${BR_NODE}" "iotlab_flash ~/A8/gnrc_border_router.elf"

echo "[FLASH] Setting up border router IPv6..."
BR_ADDR=$(ssh "root@node-${BR_NODE}" \
    "ip -6 -o addr show eth0 | grep 'scope global' | awk '{print \$4}' | cut -d/ -f1")
echo "[FLASH] Border router IPv6: $BR_ADDR"
echo "$BR_ADDR" > /tmp/br_addr

flash_m3_nodes() {
    local elf=$1
    local node_list=("${@:2}")
    local nums=""
    for n in "${node_list[@]}"; do
        nums+="${n#a8-},"
    done
    nums=${nums%,}
    echo "[FLASH] Flashing $elf on nodes: $nums"
    iotlab-ssh flash-m3 "~/A8/$elf" -l "$SITE,a8,$nums"
}

if [[ "$PHASE" == "mqtt" || "$PHASE" == "both" ]]; then
    # Nodes 0-13 → mqtt_node (BR also runs mqtt_node on M3 side for CoAP phase we skip)
    MQTT_NODES=("${NODES[@]:0:14}")
    flash_m3_nodes "mqtt_node.elf" "${MQTT_NODES[@]}"
    echo "[FLASH] MQTT-SN phase ready"
fi

if [[ "$PHASE" == "coap" || "$PHASE" == "both" ]]; then
    COAP_NODES=("${NODES[@]:0:14}")
    flash_m3_nodes "coap_node.elf" "${COAP_NODES[@]}"
    echo "[FLASH] CoAP phase ready"
fi

echo ""
echo "[FLASH] Summary:"
echo "  Border router : $BR_NODE (IPv6: $BR_ADDR)"
echo "  Sensor nodes  : ${NODES[*]:1:13}"
