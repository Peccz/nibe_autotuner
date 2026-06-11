#!/usr/bin/env python3
"""
Månadsrapport: vad GM-optimeringen sparar i kronor mot prisoaptimerad baseline.

Read-only. Körning:
  PYTHONPATH=src python scripts/savings_report.py
"""
import sys

from data.database import init_db, get_session
from services.savings_report import monthly_summary


def main() -> int:
    init_db()
    session = get_session()
    rows = monthly_summary(session)
    if not rows:
        print("Ingen daily_performance-data hittades")
        return 1

    print(f"{'Månad':8} {'Dygn':>4} {'Med data':>8} {'Faktisk kr':>11} "
          f"{'Baseline kr':>12} {'Besparing kr':>13} {'%':>7} "
          f"{'Inne °C':>8} {'Ute °C':>7}")
    print("-" * 86)
    tot_actual = tot_baseline = tot_savings = 0.0
    for m in rows:
        pct = f"{m['savings_percent']:+.1f}" if m["savings_percent"] is not None else "-"
        indoor = f"{m['avg_indoor']:.1f}" if m["avg_indoor"] is not None else "-"
        outdoor = f"{m['avg_outdoor']:.1f}" if m["avg_outdoor"] is not None else "-"
        print(f"{m['month']:8} {m['days']:>4} {m['days_with_savings']:>8} "
              f"{m['actual_cost']:>11.2f} {m['baseline_cost']:>12.2f} "
              f"{m['savings_sek']:>+13.2f} {pct:>7} {indoor:>8} {outdoor:>7}")
        tot_actual += m["actual_cost"]
        tot_baseline += m["baseline_cost"]
        tot_savings += m["savings_sek"]

    print("-" * 86)
    tot_pct = (tot_savings / tot_baseline * 100.0) if tot_baseline > 0 else 0.0
    print(f"{'TOTALT':8} {'':>4} {'':>8} {tot_actual:>11.2f} {tot_baseline:>12.2f} "
          f"{tot_savings:>+13.2f} {tot_pct:>+6.1f}%")
    print("\nBaseline = samma kompressorenergi fördelad efter värmebehov i stället "
          "för pris.\nBesparingen mäter ren prisförflyttning; varmvatten ingår på "
          "båda sidor (konservativt).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
