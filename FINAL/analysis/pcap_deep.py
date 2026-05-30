#!/usr/bin/env python3
"""
Deep packet inspection of MQTT-SN and CoAP pcap files.
Uses CoAP message-ID matching and MQTT-SN message-type inspection
for accurate RTT and PDR calculation.
"""
import struct
from pathlib import Path
from collections import defaultdict

from scapy.all import rdpcap, UDP, IPv6, Raw

RESULTS = Path(__file__).parent.parent / "results"
MQTTSN_PORT = 1883
COAP_PORT   = 5683

# ── CoAP message types ──────────────────────────────────────────────
CON, NON, ACK, RST = 0, 1, 2, 3
COAP_TYPE = {CON: "CON", NON: "NON", ACK: "ACK", RST: "RST"}

def parse_coap(raw):
    """Returns (ver, type, tkl, code, msg_id, token) or None."""
    if len(raw) < 4: return None
    b0 = raw[0]
    ver  = (b0 >> 6) & 0x3
    typ  = (b0 >> 4) & 0x3
    tkl  = b0 & 0xF
    code = raw[1]
    mid  = struct.unpack("!H", raw[2:4])[0]
    token = raw[4:4+tkl] if len(raw) >= 4+tkl else b""
    return ver, typ, code, mid, token

# ── MQTT-SN message types ─────────────────────────────────────────
MQTTSN_TYPES = {
    0x04: "CONNECT",    0x05: "CONNACK",
    0x0A: "REGISTER",   0x0B: "REGACK",
    0x0C: "PUBLISH",    0x0D: "PUBACK",
    0x12: "SUBSCRIBE",  0x13: "SUBACK",
    0x16: "PINGREQ",    0x17: "PINGRESP",
    0x18: "DISCONNECT",
}

def parse_mqttsn(raw):
    if len(raw) < 2: return None
    length = raw[0]
    mtype  = raw[1]
    return length, mtype, MQTTSN_TYPES.get(mtype, f"0x{mtype:02X}")


def analyze_coap(label, pkts):
    udp_pkts = [(p, float(p.time)) for p in pkts if UDP in p]
    proto_pkts = [(p, t) for p, t in udp_pkts
                  if p[UDP].dport == COAP_PORT or p[UDP].sport == COAP_PORT]

    pending = {}      # msg_id → (send_time, is_con)
    rtts    = []
    sent_con = sent_non = 0
    acked = 0
    type_counts = defaultdict(int)

    for p, ts in proto_pkts:
        if not (p.haslayer(Raw) or p.haslayer(UDP)): continue
        try:
            raw = bytes(p[UDP].payload)
        except Exception:
            continue
        parsed = parse_coap(raw)
        if not parsed: continue
        ver, typ, code, mid, token = parsed
        type_counts[COAP_TYPE.get(typ, "?")] += 1

        direction = "tx" if p[UDP].dport == COAP_PORT else "rx"

        if direction == "tx":
            if typ == CON:
                sent_con += 1
                pending[mid] = ts
            elif typ == NON:
                sent_non += 1
        elif direction == "rx":
            if typ == ACK and mid in pending:
                rtt = (ts - pending.pop(mid)) * 1000
                if 0 < rtt < 10000:
                    rtts.append(rtt)
                    acked += 1

    total_sent = sent_con + sent_non
    pdr = acked / sent_con * 100 if sent_con > 0 else 0

    return {
        "label": label,
        "proto": "CoAP",
        "total_pkts": len(pkts),
        "sent_con": sent_con,
        "sent_non": sent_non,
        "acked": acked,
        "pdr": round(pdr, 2),
        "rtt_n": len(rtts),
        "rtt_avg": round(sum(rtts)/len(rtts), 2) if rtts else 0,
        "rtt_med": round(sorted(rtts)[len(rtts)//2], 2) if rtts else 0,
        "rtt_min": round(min(rtts), 2) if rtts else 0,
        "rtt_max": round(max(rtts), 2) if rtts else 0,
        "rtt_p95": round(sorted(rtts)[int(len(rtts)*0.95)], 2) if len(rtts) > 1 else (max(rtts) if rtts else 0),
        "rtt_std": round((sum((x-sum(rtts)/len(rtts))**2 for x in rtts)/len(rtts))**0.5, 2) if len(rtts) > 1 else 0,
        "type_counts": dict(type_counts),
    }


def analyze_mqttsn(label, pkts):
    udp_pkts = [(p, float(p.time)) for p in pkts if UDP in p]
    proto_pkts = [(p, t) for p, t in udp_pkts
                  if p[UDP].dport == MQTTSN_PORT or p[UDP].sport == MQTTSN_PORT]

    type_counts = defaultdict(int)
    publish_times = []   # PUBLISH from client (dport=1883)
    puback_times  = []   # PUBACK  from broker (sport=1883)
    all_pingreq_ts = []  # all PINGREQ timestamps (direction-agnostic)
    all_pingresp_ts = [] # all PINGRESP timestamps
    pingresp_rtts = []

    for p, ts in proto_pkts:
        try:
            raw = bytes(p[UDP].payload)
        except Exception:
            continue
        parsed = parse_mqttsn(raw)
        if not parsed: continue
        length, mtype, mname = parsed
        type_counts[mname] += 1

        direction = "tx" if p[UDP].dport == MQTTSN_PORT else "rx"

        if mtype == 0x0C and direction == "tx":   # PUBLISH client→broker
            publish_times.append(ts)
        elif mtype == 0x0D and direction == "rx":  # PUBACK broker→client
            puback_times.append(ts)
        elif mtype == 0x16:  # PINGREQ (any direction)
            all_pingreq_ts.append(ts)
        elif mtype == 0x17:  # PINGRESP (any direction)
            all_pingresp_ts.append(ts)

    # Match PINGREQ→PINGRESP pairs
    j = 0
    for req_ts in sorted(all_pingreq_ts):
        for k in range(j, len(all_pingresp_ts)):
            dt = (all_pingresp_ts[k] - req_ts) * 1000
            if 0 < dt < 5000:
                pingresp_rtts.append(dt)
                j = k + 1
                break

    # RTT from PUBLISH→PUBACK (QoS-1, sequential pairing)
    rtts = []
    j = 0
    for pt in publish_times:
        for k in range(j, len(puback_times)):
            dt = (puback_times[k] - pt) * 1000
            if 0 < dt < 5000:
                rtts.append(dt)
                j = k + 1
                break

    # Fall back to PINGREQ/PINGRESP RTT when QoS-0 (no PUBACKs)
    if not rtts and pingresp_rtts:
        rtts = pingresp_rtts

    # PDR: QoS-1 → PUBACK/PUBLISH; QoS-0 → PINGRESP/PINGREQ
    if publish_times and puback_times:
        pdr = len(puback_times) / len(publish_times) * 100
    elif all_pingreq_ts:
        pdr = len(all_pingresp_ts) / len(all_pingreq_ts) * 100
    else:
        pdr = 0

    return {
        "label": label,
        "proto": "MQTTSN",
        "total_pkts": len(pkts),
        "sent_pub": len(publish_times) or len(all_pingreq_ts),
        "puback":   len(puback_times)  or len(all_pingresp_ts),
        "pdr": round(pdr, 2),
        "rtt_n": len(rtts),
        "rtt_avg": round(sum(rtts)/len(rtts), 2) if rtts else 0,
        "rtt_med": round(sorted(rtts)[len(rtts)//2], 2) if rtts else 0,
        "rtt_min": round(min(rtts), 2) if rtts else 0,
        "rtt_max": round(max(rtts), 2) if rtts else 0,
        "rtt_p95": round(sorted(rtts)[int(len(rtts)*0.95)], 2) if len(rtts) > 1 else (max(rtts) if rtts else 0),
        "rtt_std": round((sum((x-sum(rtts)/len(rtts))**2 for x in rtts)/len(rtts))**0.5, 2) if len(rtts) > 1 else 0,
        "type_counts": dict(type_counts),
    }


def print_results(results):
    print("\n" + "="*90)
    print(f"{'Label':<18} {'Proto':<8} {'Pkts':>5} {'Sent':>5} {'Rcvd':>5} "
          f"{'PDR%':>6} {'RTT avg':>9} {'RTT med':>9} {'RTT p95':>9} {'n':>4}")
    print("-"*90)
    for r in results:
        sent = r.get("sent_con", r.get("sent_pub", 0))
        rcvd = r.get("acked",    r.get("puback",   0))
        print(f"{r['label']:<18} {r['proto']:<8} {r['total_pkts']:>5} {sent:>5} {rcvd:>5} "
              f"{r['pdr']:>6.1f} "
              f"{r['rtt_avg']:>8.1f}ms "
              f"{r['rtt_med']:>8.1f}ms "
              f"{r['rtt_p95']:>8.1f}ms "
              f"{r['rtt_n']:>4}")
        print(f"  {'Paket tipleri:':15} {r['type_counts']}")
    print("="*90)


def save_csv(results):
    import csv
    out = RESULTS / "deep_analysis.csv"
    fields = ["label", "proto", "total_pkts", "pdr",
              "rtt_avg", "rtt_med", "rtt_min", "rtt_max", "rtt_p95", "rtt_std", "rtt_n"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)
    print(f"\nDetaylı CSV → {out}")


def plot_deep(results):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("(matplotlib yok)")
        return

    topos  = ["tree", "linear", "star"]
    protos = ["MQTTSN", "CoAP"]
    colors = {"MQTTSN": "#1565C0", "CoAP": "#E65100"}

    def get(proto, topo, key):
        lbl = f"{'MQTTSN' if proto=='MQTTSN' else 'CoAP'}_{topo}"
        for r in results:
            if r["label"] == lbl:
                return r.get(key, 0)
        return 0

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("MQTT-SN vs CoAP\nFIT IoT-LAB A8-M3 — 15 Node — Tree/Linear/Star",
                 fontsize=13, fontweight="bold")

    x  = np.arange(len(topos))
    bw = 0.35

    # RTT avg with error bars
    ax = axes[0, 0]
    for i, proto in enumerate(protos):
        vals = [get(proto, t, "rtt_avg") for t in topos]
        stds = [get(proto, t, "rtt_std") for t in topos]
        ax.bar(x + i*bw, vals, bw, label=proto, color=colors[proto], alpha=0.85)
        ax.errorbar(x + i*bw, vals, yerr=stds, fmt="none", color="black", capsize=4)
    ax.set_xticks(x + bw/2); ax.set_xticklabels([t.capitalize() for t in topos])
    ax.set_ylabel("RTT (ms)"); ax.set_title("Ortalama RTT ± Std")
    ax.legend(); ax.grid(True, alpha=0.3, axis="y")

    # PDR
    ax = axes[0, 1]
    for i, proto in enumerate(protos):
        vals = [get(proto, t, "pdr") for t in topos]
        ax.bar(x + i*bw, vals, bw, label=proto, color=colors[proto], alpha=0.85)
        for j, v in enumerate(vals):
            ax.text(x[j] + i*bw, v + 1, f"{v:.0f}%", ha="center", fontsize=8)
    ax.set_xticks(x + bw/2); ax.set_xticklabels([t.capitalize() for t in topos])
    ax.set_ylabel("PDR (%)"); ax.set_ylim(0, 115); ax.set_title("Paket İletim Oranı (PDR)")
    ax.legend(); ax.grid(True, alpha=0.3, axis="y")

    # RTT p95
    ax = axes[1, 0]
    for i, proto in enumerate(protos):
        vals = [get(proto, t, "rtt_p95") for t in topos]
        ax.bar(x + i*bw, vals, bw, label=proto, color=colors[proto], alpha=0.85)
    ax.set_xticks(x + bw/2); ax.set_xticklabels([t.capitalize() for t in topos])
    ax.set_ylabel("RTT p95 (ms)"); ax.set_title("95. Yüzdelik RTT")
    ax.legend(); ax.grid(True, alpha=0.3, axis="y")

    # Total packet count
    ax = axes[1, 1]
    for i, proto in enumerate(protos):
        vals = [get(proto, t, "total_pkts") for t in topos]
        ax.bar(x + i*bw, vals, bw, label=proto, color=colors[proto], alpha=0.85)
    ax.set_xticks(x + bw/2); ax.set_xticklabels([t.capitalize() for t in topos])
    ax.set_ylabel("Paket sayısı"); ax.set_title("Toplam Yakalanan Paket")
    ax.legend(); ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    out = RESULTS / "deep_comparison.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Grafik → {out}")


def main():
    files = {
        "MQTTSN_tree":   ("mqttsn", "mqttsn_tree.pcap"),
        "MQTTSN_linear": ("mqttsn", "mqttsn_linear.pcap"),
        "MQTTSN_star":   ("mqttsn", "mqttsn_star.pcap"),
        "CoAP_tree":     ("coap",   "coap_tree.pcap"),
        "CoAP_linear":   ("coap",   "coap_linear.pcap"),
        "CoAP_star":     ("coap",   "coap_star.pcap"),
    }

    results = []
    for label, (proto, fname) in files.items():
        path = RESULTS / fname
        if not path.exists():
            print(f"[SKIP] {fname}")
            continue
        pkts = rdpcap(str(path))
        print(f"[{label}] {len(pkts)} paket yüklendi")
        if proto == "coap":
            r = analyze_coap(label, pkts)
        else:
            r = analyze_mqttsn(label, pkts)
        results.append(r)

    print_results(results)
    save_csv(results)
    plot_deep(results)


if __name__ == "__main__":
    main()
