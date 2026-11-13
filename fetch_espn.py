"""Fetch ESPN fantasy league data and save raw JSON snapshots.

Usage: python fetch_espn.py [--season 2026]
Saves to data/raw/<season>/.
"""
import argparse
import json
from pathlib import Path

import requests

LEAGUE_ID = 639506
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league}"

HEADERS = {"User-Agent": "Mozilla/5.0 (fantasy-metrics)"}


def get(season, params, extra_headers=None):
    url = BASE.format(season=season, league=LEAGUE_ID)
    h = dict(HEADERS)
    if extra_headers:
        h.update(extra_headers)
    r = requests.get(url, params=params, headers=h, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    args = ap.parse_args()
    season = args.season

    out = Path(__file__).parent / "data" / "raw" / str(season)
    out.mkdir(parents=True, exist_ok=True)

    # League settings + teams + schedule-level scores
    core = get(season, {"view": ["mSettings", "mTeam", "mMatchupScore", "mStatus"]})
    (out / "core.json").write_text(json.dumps(core), encoding="utf-8")
    current_week = core["scoringPeriodId"]
    reg_season_weeks = core["settings"]["scheduleSettings"]["matchupPeriodCount"]
    print(f"league={core['settings']['name']} currentWeek={current_week} regWeeks={reg_season_weeks}")

    # Draft
    draft = get(season, {"view": "mDraftDetail"})
    (out / "draft.json").write_text(json.dumps(draft), encoding="utf-8")
    picks = draft.get("draftDetail", {}).get("picks", [])
    print(f"draft picks: {len(picks)}")

    # Weekly rosters/lineups (completed weeks only)
    completed = min(current_week - 1, reg_season_weeks)
    for wk in range(1, completed + 1):
        data = get(season, {"view": ["mMatchup", "mMatchupScore"], "scoringPeriodId": wk})
        (out / f"week_{wk:02d}.json").write_text(json.dumps(data), encoding="utf-8")
        print(f"saved week {wk}")

    # Transactions: ESPN only serves a recent window, so archive cumulatively
    tx_path = out / "transactions.json"
    seen = {}
    if tx_path.exists():
        seen = {t["id"]: t for t in json.loads(tx_path.read_text(encoding="utf-8"))}
    txs = get(season, {"view": "mTransactions2"}).get("transactions", [])
    for t in txs:
        if t.get("type") in ("ROSTER", "FUTURE_ROSTER"):
            continue  # lineup moves, not acquisitions
        seen[t["id"]] = t
    tx_path.write_text(json.dumps(sorted(seen.values(), key=lambda t: t.get("proposedDate", 0))),
                       encoding="utf-8")
    print(f"transactions archived: {len(seen)}")

    # Pro team schedules (bye weeks)
    pro = requests.get(
        f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}?view=proTeamSchedules_wl",
        headers=HEADERS, timeout=30).json()
    byes = {t["id"]: t.get("byeWeek") for t in pro["settings"]["proTeams"]}
    (out / "byes.json").write_text(json.dumps(byes), encoding="utf-8")
    print("byes saved")

    # Player info incl. ADP + injury status (large filter via header)
    flt = {
        "players": {
            "limit": 600,
            "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
        }
    }
    players = get(
        season,
        {"view": "kona_player_info"},
        extra_headers={"x-fantasy-filter": json.dumps(flt)},
    )
    (out / "players.json").write_text(json.dumps(players), encoding="utf-8")
    print(f"players: {len(players.get('players', []))}")


if __name__ == "__main__":
    main()
