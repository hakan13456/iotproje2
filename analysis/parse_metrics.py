#!/usr/bin/env python3
"""
Parse serial CSV logs and produce comparison statistics + plots.

Input CSV columns (from firmware printf):
  CSV,MQTTSN,<seq>,<send_ms>,<recv_ms>,<rtt_ms>
  CSV,COAP,<seq>,<send_ms>,<recv_ms>,<rtt_ms>

Usage:
  python3 parse_metrics.py results/mqtt_csv_*.csv results/coap_csv_*.csv
"""
import sys
import os
import csv
import statistics
import glob
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent / "results"


def load_csv(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) < 6 or parts[0] != "CSV":
                continue
            proto   = parts[1]
            seq     = int(parts[2])
            send_ms = int(parts[3])
            try:
                recv_ms = int(parts[4])
                rtt_ms  = int(parts[5])
                lost = False
            except ValueError:
                recv_ms = 0
                rtt_ms  = 0
                lost = True
            rows.append({
                "proto": proto, "seq": seq,
                "send_ms": send_ms, "recv_ms": recv_ms,
                "rtt_ms": rtt_ms, "lost": lost
            })
    return rows


def stats(rows):
    delivered = [r for r in rows if not r["lost"]]
    rtts = [r["rtt_ms"] for r in delivered]
    total = len(rows)
    recv  = len(delivered)
    pdr   = recv / total * 100 if total > 0 else 0
    return {
        "total": total,
        "recv":  recv,
        "lost":  total - recv,
        "pdr":   pdr,
        "rtt_avg":    statistics.mean(rtts)           if rtts else 0,
        "rtt_median": statistics.median(rtts)         if rtts else 0,
        "rtt_stdev":  statistics.stdev(rtts)          if len(rtts) > 1 else 0,
        "rtt_min":    min(rtts)                        if rtts else 0,
        "rtt_max":    max(rtts)                        if rtts else 0,
        "rtt_p95":    sorted(rtts)[int(len(rtts)*0.95)] if rtts else 0,
    }


def print_table(mqtt_s, coap_s):
    w = 20
    print("\n" + "="*55)
    print(f"{'Metric':<{w}} {'MQTT-SN':>12} {'CoAP':>12}")
    print("="*55)
    metrics = [
        ("Sent packets",    "total",      "",    "d"),
        ("Received",        "recv",       "",    "d"),
        ("Lost",            "lost",       "",    "d"),
        ("PDR (%)",         "pdr",        "",    ".2f"),
        ("RTT avg (ms)",    "rtt_avg",    "",    ".2f"),
        ("RTT median (ms)", "rtt_median", "",    ".2f"),
        ("RTT stdev (ms)",  "rtt_stdev",  "",    ".2f"),
        ("RTT min (ms)",    "rtt_min",    "",    "d"),
        ("RTT max (ms)",    "rtt_max",    "",    "d"),
        ("RTT p95 (ms)",    "rtt_p95",    "",    "d"),
    ]
    for label, key, unit, fmt in metrics:
        mv = mqtt_s[key]
        cv = coap_s[key]
        mstr = format(mv, fmt)
        cstr = format(cv, fmt)
        print(f"{label:<{w}} {mstr:>12} {cstr:>12}")
    print("="*55)


def save_summary_csv(mqtt_rows, coap_rows, mqtt_s, coap_s):
    out = RESULTS_DIR / "comparison_summary.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "mqtt_sn", "coap"])
        for k in mqtt_s:
            w.writerow([k, round(mqtt_s[k], 4), round(coap_s[k], 4)])
    print(f"\nSummary CSV → {out}")

    # per-packet CSV
    all_out = RESULTS_DIR / "all_packets.csv"
    with open(all_out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["proto", "seq", "send_ms", "recv_ms", "rtt_ms", "lost"])
        for r in mqtt_rows + coap_rows:
            w.writerow([r["proto"], r["seq"], r["send_ms"],
                        r["recv_ms"], r["rtt_ms"], int(r["lost"])])
    print(f"All packets CSV → {all_out}")


def try_plot(mqtt_rows, coap_rows):
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("(matplotlib not installed — skipping plots)")
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("MQTT-SN vs CoAP — FIT IoT-LAB Tree Topology")

    # RTT over time
    ax = axes[0]
    for rows, label, color in [(mqtt_rows, "MQTT-SN", "blue"),
                                (coap_rows, "CoAP",    "orange")]:
        valid = [r for r in rows if not r["lost"]]
        if valid:
            ax.plot([r["seq"] for r in valid],
                    [r["rtt_ms"] for r in valid],
                    ".", markersize=3, label=label, color=color, alpha=0.6)
    ax.set_xlabel("Sequence number")
    ax.set_ylabel("RTT (ms)")
    ax.set_title("RTT over time")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # RTT CDF
    ax = axes[1]
    for rows, label, color in [(mqtt_rows, "MQTT-SN", "blue"),
                                (coap_rows, "CoAP",    "orange")]:
        rtts = sorted(r["rtt_ms"] for r in rows if not r["lost"])
        if rtts:
            cdf = np.arange(1, len(rtts)+1) / len(rtts)
            ax.plot(rtts, cdf, label=label, color=color)
    ax.set_xlabel("RTT (ms)")
    ax.set_ylabel("CDF")
    ax.set_title("RTT CDF")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # PDR bar chart
    ax = axes[2]
    protos = ["MQTT-SN", "CoAP"]
    from analysis_data import mqtt_s, coap_s  # noqa — passed via closure below

    # inline
    mqtt_s_l = stats(mqtt_rows)
    coap_s_l = stats(coap_rows)
    pdrs   = [mqtt_s_l["pdr"], coap_s_l["pdr"]]
    colors = ["blue", "orange"]
    bars = ax.bar(protos, pdrs, color=colors, alpha=0.7)
    for bar, val in zip(bars, pdrs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f"{val:.1f}%", ha="center")
    ax.set_ylabel("PDR (%)")
    ax.set_ylim(0, 105)
    ax.set_title("Packet Delivery Ratio")
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    out = RESULTS_DIR / "comparison_plot.png"
    plt.savefig(out, dpi=150)
    print(f"Plot → {out}")
    plt.show()


def main():
    args = sys.argv[1:]
    if not args:
        # auto-detect latest files
        mqtt_files = sorted(glob.glob(str(RESULTS_DIR / "mqtt_csv_*.csv")))
        coap_files = sorted(glob.glob(str(RESULTS_DIR / "coap_csv_*.csv")))
        if not mqtt_files or not coap_files:
            print("No CSV files found. Usage: python3 parse_metrics.py <mqtt.csv> <coap.csv>")
            sys.exit(1)
        mqtt_file, coap_file = mqtt_files[-1], coap_files[-1]
    else:
        mqtt_file, coap_file = args[0], args[1]

    print(f"MQTT-SN file: {mqtt_file}")
    print(f"CoAP file:    {coap_file}")

    mqtt_rows = load_csv(mqtt_file)
    coap_rows = load_csv(coap_file)

    mqtt_s = stats(mqtt_rows)
    coap_s = stats(coap_rows)

    print_table(mqtt_s, coap_s)
    save_summary_csv(mqtt_rows, coap_rows, mqtt_s, coap_s)
    try_plot(mqtt_rows, coap_rows)


if __name__ == "__main__":
    main()
