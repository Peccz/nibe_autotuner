#!/usr/bin/env python3
"""
Backfill av besparingskolumnerna i daily_performance för historiska dygn.

Planhistoriken sparas bara ~48h, så historiska timpriser hämtas från
elprisetjustnu.se via price_service (en request per dygn, cache:as).
Skriver baseline_kwh/baseline_cost_sek/savings_sek/savings_percent för
rader där savings_sek är NULL; actual_cost_sek fylls bara i om den saknas.

Körning:
  PYTHONPATH=src python scripts/backfill_savings.py            # dry-run
  PYTHONPATH=src python scripts/backfill_savings.py --execute  # skriv
"""
import argparse
import sys
import time

from data.database import init_db, get_session
from data.models import Device
from data.performance_model import DailyPerformance
from services.savings_report import compute_savings_for_day

REQUEST_PAUSE_S = 0.4  # var snäll mot elprisetjustnu.se


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="Skriv till databasen (default: dry-run)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max antal dygn att behandla (0 = alla)")
    parser.add_argument("--recompute-all", action="store_true",
                        help="Räkna om ALLA dygn (även de med gamla "
                             "ai_evaluator-värden) för en metodkonsistent serie")
    args = parser.parse_args()

    init_db()
    session = get_session()
    device = session.query(Device).first()
    if not device:
        print("Ingen device i databasen — avbryter")
        return 1

    query = session.query(DailyPerformance)
    if not args.recompute_all:
        query = query.filter(DailyPerformance.savings_sek.is_(None))
    rows = query.order_by(DailyPerformance.date).all()
    if args.limit:
        rows = rows[: args.limit]

    print(f"{len(rows)} dygn saknar besparingsdata "
          f"({'SKRIVER' if args.execute else 'dry-run'})")

    filled = skipped = 0
    for dp in rows:
        sav = compute_savings_for_day(session, device.id, dp.date)
        if sav is None:
            skipped += 1
            print(f"  {dp.date.date()}: otillräckligt underlag — hoppar över")
        else:
            filled += 1
            print(f"  {dp.date.date()}: actual {sav.actual_cost_sek:7.2f} kr, "
                  f"baseline {sav.baseline_cost_sek:7.2f} kr, "
                  f"besparing {sav.savings_sek:+7.2f} kr ({sav.savings_percent:+.1f} %)")
            if args.execute:
                dp.baseline_kwh = sav.baseline_kwh
                dp.baseline_cost_sek = sav.baseline_cost_sek
                dp.savings_sek = sav.savings_sek
                dp.savings_percent = sav.savings_percent
                if args.recompute_all:
                    # Metodkonsistens: kostnads-/energisidan ska komma från
                    # samma modell som baseline (gamla ai_evaluator-värden
                    # finns kvar i deploy-backupen).
                    dp.actual_kwh = sav.actual_kwh
                    dp.actual_cost_sek = sav.actual_cost_sek
                elif dp.actual_cost_sek is None:
                    dp.actual_cost_sek = sav.actual_cost_sek
                session.commit()
        time.sleep(REQUEST_PAUSE_S)

    print(f"Klart: {filled} ifyllda, {skipped} överhoppade"
          + ("" if args.execute else " (inget skrivet — dry-run)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
