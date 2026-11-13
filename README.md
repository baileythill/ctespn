# CTESPN — The Worldwide Leader in Luck™

A parody-SportsCenter dashboard for the **Fantasy Footballerz** ESPN league:
Luck Index, Regret Index, Coaching Report, Trade Desk, and the rest of the
programming slate. Not affiliated with ESPN. All sob stories are real.

## How it works

```
fetch_espn.py    pulls raw league data from ESPN's public API (data/raw/)
metrics.py       computes every metric -> data/metrics_<season>.json + data/league.db
export_web.py    bundles metrics + luck-trend history -> web/public/data/league.json
web/             Vite + React site (GitHub Pages)
```

A GitHub Action refreshes data and redeploys every Tuesday morning
(`.github/workflows/refresh.yml`); push to `main` also redeploys.

Manual refresh:

```bash
python fetch_espn.py && python metrics.py && python export_web.py
```

Local dev: `npm run dev` in `web/`.

## League-maintained files

- `data/overrides.json` — absences that are *not* injuries (suspensions, legal)
- `data/trades.json` — authoritative trade list (corrects auto-detection)

## The Luck Index

Five z-scored components, weighted: schedule (35%), injury (20%), close games
(15%), points-against (15%), draft vs ADP (15%). The league plays H2H plus a
weekly median game, which the math accounts for. Season-ending injuries keep
counting after a drop. Dropping C.J. Stroud is a personal choice and the Luck
Index does not cover it; see the Regret Index.
