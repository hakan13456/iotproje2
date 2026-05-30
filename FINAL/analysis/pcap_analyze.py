#!/usr/bin/env python3
"""
Analyze MQTT-SN and CoAP pcap files from FIT IoT-LAB experiments.
Extracts: packet counts, inter-arrival times, RTT estimates, PDR proxy,
          payload sizes, protocol distribution.
"""
import os
import sys
from pathlib import Path
from collections import defaultdict

try:
    from scapy.all import rdpcap, UDP, IPv6, Raw
    from scapy.layers.sixlowpan import SixLoWPAN
except ImportError:
    print("ERROR: pip install scapy")
    sys.exit(1)

RESULTS = Path(__file__).parent.parent / "results"

FILES = {
    "MQTTSN_tree":   "mqttsn_tree.pcap",
    "MQTTSN_linear": "mqttsn_linear.pcap",
    "MQTTSN_star":   "mqttsn_star.pcap",
    "CoAP_tree":     "coap_tree.pcap",
    "CoAP_linear":   "coap_linear.pcap",
    "CoAP_star":     "coap_star.pcap",
}

MQTTSN_PORT = 1883
COAP_PORT   = 5683


def analyze_pcap(label, path):
    if not path.exists():
        print(f"  [SKIP] {path.name} not found")
        return None

    try:
        pkts = rdpcap(str(path))
    except Exception as e:
        print(f"  [ERR] {path.name}: {e}")
        return None

    total = len(pkts)
    if total == 0:
        return None

    # Timestamps
    timestamps = [float(p.time) for p in pkts]
    duration   = timestamps[-1] - timestamps[0] if len(timestamps) > 1 else 0

    # Packet sizes
    sizes = [len(p) for p in pkts]

    # Inter-arrival times
    iats = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    avg_iat = sum(iats) / len(iats) if iats else 0

    # Protocol-specific counts
    udp_pkts   = [p for p in pkts if UDP in p]
    ipv6_pkts  = [p for p in pkts if IPv6 in p]

    proto = label.split("_")[0]
    target_port = MQTTSN_PORT if proto == "MQTTSN" else COAP_PORT

    proto_pkts = [p for p in udp_pkts
                  if UDP in p and (p[UDP].dport == target_port or
                                   p[UDP].sport == target_port)]

    # CoAP: separate requests (dport=5683) from responses (sport=5683)
    if proto == "CoAP":
        req_pkts  = [p for p in udp_pkts if UDP in p and p[UDP].dport == target_port]
        resp_pkts = [p for p in udp_pkts if UDP in p and p[UDP].sport == target_port]
        # RTT estimate: match requests/responses by CoAP token (raw approximation)
        # Simple approach: pair by timestamp proximity
        pdr_proxy = len(resp_pkts) / len(req_pkts) * 100 if req_pkts else 0
        rtts = []
        j = 0
        for req in req_pkts:
            for k in range(j, min(j+20, len(resp_pkts))):
                dt = float(resp_pkts[k].time) - float(req.time)
                if 0 < dt < 5.0:
                    rtts.append(dt * 1000)
                    j = k + 1
                    break
    else:
        # MQTT-SN: publish (client→broker dport=1883) and puback/suback (broker→client)
        req_pkts  = [p for p in udp_pkts if UDP in p and p[UDP].dport == target_port]
        resp_pkts = [p for p in udp_pkts if UDP in p and p[UDP].sport == target_port]
        pdr_proxy = len(resp_pkts) / len(req_pkts) * 100 if req_pkts else 0
        rtts = []
        j = 0
        for req in req_pkts:
            for k in range(j, min(j+20, len(resp_pkts))):
                dt = float(resp_pkts[k].time) - float(req.time)
                if 0 < dt < 5.0:
                    rtts.append(dt * 1000)
                    j = k + 1
                    break

    avg_rtt    = sum(rtts) / len(rtts)           if rtts else 0
    median_rtt = sorted(rtts)[len(rtts)//2]      if rtts else 0
    max_rtt    = max(rtts)                        if rtts else 0
    min_rtt    = min(rtts)                        if rtts else 0
    p95_rtt    = sorted(rtts)[int(len(rtts)*0.95)] if len(rtts) > 1 else max_rtt
    stdev_rtt  = (sum((x - avg_rtt)**2 for x in rtts) / len(rtts))**0.5 if rtts else 0

    return {
        "label":       label,
        "file":        path.name,
        "total_pkts":  total,
        "ipv6_pkts":   len(ipv6_pkts),
        "proto_pkts":  len(proto_pkts),
        "req_pkts":    len(req_pkts),
        "resp_pkts":   len(resp_pkts),
        "duration_s":  round(duration, 2),
        "avg_pkt_size": round(sum(sizes)/len(sizes), 1),
        "max_pkt_size": max(sizes),
        "min_pkt_size": min(sizes),
        "avg_iat_ms":  round(avg_iat * 1000, 2),
        "pdr_proxy":   round(pdr_proxy, 2),
        "rtt_count":   len(rtts),
        "rtt_avg_ms":  round(avg_rtt, 2),
        "rtt_med_ms":  round(median_rtt, 2),
        "rtt_min_ms":  round(min_rtt, 2),
        "rtt_max_ms":  round(max_rtt, 2),
        "rtt_p95_ms":  round(p95_rtt, 2),
        "rtt_std_ms":  round(stdev_rtt, 2),
        "throughput_pps": round(total / duration, 2) if duration > 0 else 0,
    }


def print_table(results):
    print("\n" + "="*100)
    hdr = f"{'Label':<18} {'Pkts':>6} {'Req':>5} {'Resp':>5} {'PDR%':>6} " \
          f"{'RTT avg':>8} {'RTT med':>8} {'RTT p95':>8} {'RTT std':>8} {'Dur(s)':>7}"
    print(hdr)
    print("-"*100)
    for r in results:
        if r is None: continue
        print(f"{r['label']:<18} {r['total_pkts']:>6} {r['req_pkts']:>5} "
              f"{r['resp_pkts']:>5} {r['pdr_proxy']:>6.1f} "
              f"{r['rtt_avg_ms']:>7.1f}ms {r['rtt_med_ms']:>7.1f}ms "
              f"{r['rtt_p95_ms']:>7.1f}ms {r['rtt_std_ms']:>7.1f}ms "
              f"{r['duration_s']:>7.1f}")
    print("="*100)


def save_csv(results):
    import csv
    out = RESULTS / "pcap_analysis.csv"
    keys = ["label", "file", "total_pkts", "req_pkts", "resp_pkts",
            "pdr_proxy", "rtt_avg_ms", "rtt_med_ms", "rtt_min_ms",
            "rtt_max_ms", "rtt_p95_ms", "rtt_std_ms", "rtt_count",
            "duration_s", "avg_pkt_size", "avg_iat_ms", "throughput_pps"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in results:
            if r: w.writerow(r)
    print(f"\nCSV → {out}")
    return out


def plot(results):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("(matplotlib yok — grafik atlandı)")
        return

    topos = ["tree", "linear", "star"]
    protos = ["MQTTSN", "CoAP"]
    colors = {"MQTTSN": "#2196F3", "CoAP": "#FF9800"}
    hatches = {"tree": "", "linear": "//", "star": "xx"}

    def get(proto, topo, key):
        for r in results:
            if r and r["label"] == f"{proto}_{topo}":
                return r.get(key, 0)
        return 0

    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    fig.suptitle("MQTT-SN vs CoAP — FIT IoT-LAB A8-M3\n"
                 "Tree / Linear / Star Topologies", fontsize=13, fontweight="bold")

    # --- RTT avg ---
    ax = axes[0]
    x = np.arange(len(topos))
    w = 0.35
    for i, proto in enumerate(protos):
        vals = [get(proto, t, "rtt_avg_ms") for t in topos]
        errs = [get(proto, t, "rtt_std_ms") for t in topos]
        bars = ax.bar(x + i*w, vals, w, label=proto,
                      color=colors[proto], alpha=0.85, capsize=4)
        ax.errorbar(x + i*w, vals, yerr=errs, fmt="none",
                    color="black", capsize=4, linewidth=1)
    ax.set_xticks(x + w/2)
    ax.set_xticklabels([t.capitalize() for t in topos])
    ax.set_ylabel("Average RTT (ms)")
    ax.set_title("Average RTT by Topology")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")

    # --- PDR ---
    ax = axes[1]
    for i, proto in enumerate(protos):
        vals = [get(proto, t, "pdr_proxy") for t in topos]
        ax.bar(x + i*w, vals, w, label=proto,
               color=colors[proto], alpha=0.85)
    ax.set_xticks(x + w/2)
    ax.set_xticklabels([t.capitalize() for t in topos])
    ax.set_ylabel("PDR (%)")
    ax.set_ylim(0, 110)
    ax.set_title("Packet Delivery Ratio")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")

    # --- RTT CDF (tree topology only) ---
    ax = axes[2]
    for proto in protos:
        for r in results:
            if r and r["label"] == f"{proto}_tree" and r["rtt_count"] > 0:
                # Re-read to get individual RTTs for CDF — not stored, use median/p95 approx
                # Just plot what we have as reference points
                pts = [r["rtt_min_ms"], r["rtt_med_ms"], r["rtt_p95_ms"], r["rtt_max_ms"]]
                cdf = [0.05, 0.50, 0.95, 1.00]
                ax.plot(pts, cdf, "o-", label=f"{proto} (tree)",
                        color=colors[proto], linewidth=2, markersize=6)
    ax.set_xlabel("RTT (ms)")
    ax.set_ylabel("CDF")
    ax.set_title("RTT CDF — Tree Topology")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = RESULTS / "comparison_plot.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Grafik → {out}")


def main():
    print("FIT IoT-LAB PCAP Analysis — MQTT-SN vs CoAP")
    print(f"Analiz edilen dosyalar: {RESULTS}/")
    results = []
    for label, fname in FILES.items():
        path = RESULTS / fname
        print(f"\n[{label}] {fname}")
        r = analyze_pcap(label, path)
        results.append(r)
        if r:
            print(f"  Paketler: {r['total_pkts']}  "
                  f"Req/Resp: {r['req_pkts']}/{r['resp_pkts']}  "
                  f"PDR: {r['pdr_proxy']:.1f}%  "
                  f"RTT avg: {r['rtt_avg_ms']:.1f}ms  "
                  f"Süre: {r['duration_s']:.1f}s")

    print_table(results)
    csv_path = save_csv(results)
    plot(results)
    return results


if __name__ == "__main__":
    main()
