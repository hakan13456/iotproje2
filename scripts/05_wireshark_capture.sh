#!/bin/bash
# Capture 802.15.4 / 6LoWPAN traffic from A8 nodes via tshark
# The A8 Linux OS can sniff the wireless interface used by the M3 radio.
# Output: .pcapng file ready for Wireshark analysis.
#
# Usage: ./05_wireshark_capture.sh <node_id> [duration_seconds]
set -euo pipefail

NODE=${1:-}
DURATION=${2:-60}
SITE=saclay

[[ -z "$NODE" ]] && { echo "Usage: $0 <node_id e.g. a8-18> [seconds]"; exit 1; }

PROJDIR=$(cd "$(dirname "$0")/.." && pwd)
RESULTS_DIR="$PROJDIR/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PCAP_FILE="$RESULTS_DIR/${NODE}_${TIMESTAMP}.pcapng"
mkdir -p "$RESULTS_DIR"

echo "[CAPTURE] Starting tshark on $NODE for ${DURATION}s → $PCAP_FILE"

# The AT86RF231 on A8-M3 shows up as wpan0 or at86rf231 interface on the A8 Linux
# We capture on the monitor interface and filter 6LoWPAN / CoAP / MQTT-SN
ssh "root@node-${NODE}" \
    "tshark -i wpan0 -w - -a duration:${DURATION} 2>/dev/null" > "$PCAP_FILE"

SIZE=$(du -h "$PCAP_FILE" | cut -f1)
echo "[CAPTURE] Saved: $PCAP_FILE ($SIZE)"
echo "[CAPTURE] Open in Wireshark: wireshark $PCAP_FILE"
echo ""
echo "[CAPTURE] Quick tshark summary:"
tshark -r "$PCAP_FILE" \
    -q \
    -z "io,stat,1" \
    -z "conv,ipv6" 2>/dev/null | head -40
