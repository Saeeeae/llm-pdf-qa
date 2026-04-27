"""
Analyze Locust CSV results and save a latency chart.

Usage:
    python loadtest/analyze.py loadtest/results/sustained
"""
import sys
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main(prefix: str) -> None:
    stats = pd.read_csv(f"{prefix}_stats.csv")
    history = pd.read_csv(f"{prefix}_stats_history.csv")

    print(stats[["Name", "Request Count", "Failure Count", "50%", "95%", "99%"]])

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(history["Timestamp"], history["Total Median Response Time"], label="p50")
    ax.plot(history["Timestamp"], history["Total 95%"], label="p95")
    ax.set_xlabel("Time")
    ax.set_ylabel("Latency (ms)")
    ax.legend()
    ax.set_title("Load Test Latency")

    out_path = f"{prefix}_latency.png"
    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    print(f"Saved {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analyze.py <results_prefix>")
        sys.exit(1)
    main(sys.argv[1])
