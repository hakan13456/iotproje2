#!/bin/bash
# Build all firmwares for iotlab-a8-m3
# Run on saclay frontend: ssh donmez@saclay.iot-lab.info
set -euo pipefail

BOARD=iotlab-a8-m3
CHANNEL=26
RIOTBASE=${RIOTBASE:-~/A8/riot/RIOT}
PROJDIR=$(cd "$(dirname "$0")/.." && pwd)

build_fw() {
    local name=$1
    local dir=$2
    echo "[BUILD] $name ..."
    make BOARD="$BOARD" \
         DEFAULT_CHANNEL="$CHANNEL" \
         RIOTBASE="$RIOTBASE" \
         -C "$dir" clean all 2>&1 | tail -5
    echo "[BUILD] $name OK → $(ls "$dir/bin/$BOARD/"*.elf)"
}

build_fw "border_router" "$RIOTBASE/examples/gnrc_border_router"
build_fw "mqtt_node"     "$PROJDIR/firmware/mqtt_node"
build_fw "coap_node"     "$PROJDIR/firmware/coap_node"

# Copy ELFs to ~/A8/ for easy flashing
mkdir -p ~/A8
cp "$RIOTBASE/examples/gnrc_border_router/bin/$BOARD/gnrc_border_router.elf" ~/A8/
cp "$PROJDIR/firmware/mqtt_node/bin/$BOARD/mqtt_node.elf"                    ~/A8/
cp "$PROJDIR/firmware/coap_node/bin/$BOARD/coap_node.elf"                    ~/A8/
echo "[BUILD] All ELFs in ~/A8/"
ls -lh ~/A8/*.elf
