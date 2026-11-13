"""Bundle metrics JSON + luck trend history into the web app's data file.

Usage: python export_web.py [--season 2026]
Writes web/public/data/league.json.
"""
import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    args = ap.parse_args()

    metrics = json.loads(
        (ROOT / "data" / f"metrics_{args.season}.json").read_text(encoding="utf-8"))

    db = sqlite3.connect(ROOT / "data" / "league.db")
    trend = [
        {"week": w, "teamId": t, "luck": l}
        for w, t, l in db.execute(
            "SELECT through_week, team_id, luck_index FROM luck_snapshots "
            "WHERE season=? ORDER BY through_week, team_id", (args.season,))
    ]
    db.close()
    metrics["luckTrend"] = trend

    out = ROOT / "web" / "public" / "data"
    out.mkdir(parents=True, exist_ok=True)
    (out / "league.json").write_text(json.dumps(metrics), encoding="utf-8")
    print(f"exported {out / 'league.json'} (teams={len(metrics['teams'])}, "
          f"trend rows={len(trend)})")


if __name__ == "__main__":
    main()
