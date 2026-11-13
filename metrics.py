"""Compute the Luck Index and supporting metrics from raw ESPN snapshots.

League quirk: Fantasy Footballerz plays H2H plus a game vs the weekly league
median, so records have 2 results per week. Schedule luck only applies to the
H2H half (the median game can't be schedule-lucky).

Usage: python metrics.py [--season 2026]
Writes data/metrics_<season>.json and upserts weekly history into data/league.db.
"""
import argparse
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
CLOSE_GAME_MARGIN = 10.0
IR_SLOT = 21
BENCH_SLOT = 20

# Composite weights (positive component value = lucky)
WEIGHTS = {
    "schedule": 0.35,   # actual H2H wins - all-play expected wins
    "close": 0.15,      # close-game wins above expectation (50%)
    "pa": 0.15,         # points-against below league average
    "injury": 0.20,     # starter points lost to injury vs league average (inverted)
    "draft": 0.15,      # drafted players' production vs ADP expectation
}


def zscores(values_by_team):
    vals = list(values_by_team.values())
    mean = statistics.mean(vals)
    sd = statistics.pstdev(vals)
    if sd == 0:
        return {t: 0.0 for t in values_by_team}
    return {t: (v - mean) / sd for t, v in values_by_team.items()}


def load(season):
    raw = ROOT / "data" / "raw" / str(season)
    core = json.loads((raw / "core.json").read_text(encoding="utf-8"))
    draft = json.loads((raw / "draft.json").read_text(encoding="utf-8"))
    players = json.loads((raw / "players.json").read_text(encoding="utf-8"))
    weeks = {}
    for f in sorted(raw.glob("week_*.json")):
        wk = int(f.stem.split("_")[1])
        weeks[wk] = json.loads(f.read_text(encoding="utf-8"))
    return core, draft, players, weeks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--through", type=int, default=None,
                    help="compute as of this week (snapshot backfill only: "
                         "writes luck_snapshots, not the metrics JSON)")
    args = ap.parse_args()
    season = args.season

    core, draft, players_raw, weeks_raw = load(season)
    if args.through:
        weeks_raw = {w: d for w, d in weeks_raw.items() if w <= args.through}
    teams = {t["id"]: t for t in core["teams"]}
    team_names = {t["id"]: t.get("name", f"Team {t['id']}") for t in core["teams"]}
    abbrevs = {t["id"]: t.get("abbrev", "") for t in core["teams"]}

    # ---- weekly H2H scores & results -------------------------------------
    scores = defaultdict(dict)   # week -> team -> points
    opponents = defaultdict(dict)  # week -> team -> opp team id
    for m in core["schedule"]:
        if m.get("winner") in (None, "UNDECIDED") or "home" not in m or "away" not in m:
            continue
        wk = m["matchupPeriodId"]
        h, a = m["home"], m["away"]
        scores[wk][h["teamId"]] = h["totalPoints"]
        scores[wk][a["teamId"]] = a["totalPoints"]
        opponents[wk][h["teamId"]] = a["teamId"]
        opponents[wk][a["teamId"]] = h["teamId"]
    if args.through:
        scores = defaultdict(dict, {w: v for w, v in scores.items() if w <= args.through})
        opponents = defaultdict(dict, {w: v for w, v in opponents.items() if w <= args.through})
    completed_weeks = sorted(scores.keys())
    n_weeks = len(completed_weeks)
    team_ids = sorted(teams.keys())

    h2h_wins = defaultdict(int)
    median_wins = defaultdict(int)
    allplay_wins = defaultdict(float)  # fractional vs all opponents
    close_w = defaultdict(int)
    close_l = defaultdict(int)
    pa = defaultdict(float)
    pf = defaultdict(float)
    weekly_rows = []  # for db/history
    top_score_weeks = defaultdict(int)
    luckiest_wins = []   # (week, team, pts) won while scoring in bottom half
    toughest_losses = []  # lost while scoring in top half

    for wk in completed_weeks:
        wk_scores = scores[wk]
        vals = sorted(wk_scores.values())
        med = statistics.median(vals)
        n = len(wk_scores)
        top_team = max(wk_scores, key=wk_scores.get)
        top_score_weeks[top_team] += 1
        for t, pts in wk_scores.items():
            opp = opponents[wk][t]
            opp_pts = wk_scores[opp]
            won = pts > opp_pts
            pf[t] += pts
            pa[t] += opp_pts
            if won:
                h2h_wins[t] += 1
            if pts > med:
                median_wins[t] += 1
            beat = sum(1 for o, op in wk_scores.items() if o != t and pts > op)
            allplay_wins[t] += beat / (n - 1)
            if abs(pts - opp_pts) <= CLOSE_GAME_MARGIN:
                if won:
                    close_w[t] += 1
                else:
                    close_l[t] += 1
            rank = sum(1 for v in vals if v > pts) + 1  # 1 = top score
            if won and rank > n / 2:
                luckiest_wins.append({"week": wk, "teamId": t, "points": pts, "oppPoints": opp_pts, "rank": rank})
            if not won and rank <= n / 2:
                toughest_losses.append({"week": wk, "teamId": t, "points": pts, "oppPoints": opp_pts, "rank": rank})
            weekly_rows.append((season, wk, t, pts, opp, opp_pts, int(won), int(pts > med), beat / (n - 1)))

    # ---- injuries: rostered player-weeks missed --------------------------
    # A rostered player "missed" a week when his actual stat entry for that
    # scoring period has no populated stats dict (= didn't play) and his pro
    # team was not on bye. Value lost = his avg ppg in weeks he played.
    byes = {int(k): v for k, v in json.loads(
        (ROOT / "data" / "raw" / str(season) / "byes.json").read_text(encoding="utf-8")).items()}

    player_week_pts = defaultdict(dict)  # playerId -> week -> pts when played
    player_names = {}
    rosters = defaultdict(dict)  # week -> team -> [(pid, slot, played, proTeam, pts)]
    for wk, data in weeks_raw.items():
        for m in data.get("schedule", []):
            if m.get("matchupPeriodId") != wk:
                continue
            for side in ("home", "away"):
                if side not in m:
                    continue
                r = m[side].get("rosterForCurrentScoringPeriod") or {}
                rows = []
                for e in r.get("entries", []):
                    ppe = e.get("playerPoolEntry", {})
                    pl = ppe.get("player", {})
                    pid = e.get("playerId")
                    player_names[pid] = pl.get("fullName", str(pid))
                    pts = ppe.get("appliedStatTotal", 0.0) or 0.0
                    played = any(
                        s.get("scoringPeriodId") == wk and s.get("statSourceId") == 0
                        and s.get("statSplitTypeId") == 1 and s.get("stats")
                        for s in pl.get("stats", []))
                    if played:
                        player_week_pts[pid][wk] = pts
                    rows.append((pid, e.get("lineupSlotId"), played,
                                 pl.get("proTeamId"), pts, pl.get("eligibleSlots", [])))
                rosters[wk][m[side]["teamId"]] = rows

    # ---- ADP + true season totals (from kona player info) ------------------
    adp = {}
    kona_season_pts = {}
    for p in players_raw.get("players", []):
        pl = p.get("player", {})
        pid = pl["id"]
        a = (pl.get("ownership") or {}).get("averageDraftPosition")
        if a and a > 0:
            adp[pid] = a
        for s in pl.get("stats", []):
            if (s.get("statSourceId") == 0 and s.get("statSplitTypeId") == 0
                    and s.get("seasonId") == season):
                kona_season_pts[pid] = s.get("appliedTotal", 0.0)
        player_names.setdefault(pid, pl.get("fullName", str(pid)))

    # positions (defaultPositionId: 1 QB, 2 RB, 3 WR, 4 TE, 5 K, 16 D/ST)
    pos_of = {}
    for p in players_raw.get("players", []):
        pos_of[p["player"]["id"]] = p["player"].get("defaultPositionId")
    for wk, data in weeks_raw.items():
        for m in data.get("schedule", []):
            for side in ("home", "away"):
                if side not in m:
                    continue
                r = m[side].get("rosterForCurrentScoringPeriod") or {}
                for e in r.get("entries", []):
                    pl = e.get("playerPoolEntry", {}).get("player", {})
                    pos_of.setdefault(pl.get("id"), pl.get("defaultPositionId"))

    def fit_loglinear(pairs):
        """pairs of (x, y) with x already logged; returns (b0, b1)."""
        xs = [x for x, _ in pairs]
        ys = [y for _, y in pairs]
        xm, ym = statistics.mean(xs), statistics.mean(ys)
        sxx = sum((x - xm) ** 2 for x in xs)
        sxy = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
        b1 = sxy / sxx if sxx else 0.0
        return ym - b1 * xm, b1

    # fits of season points ~ log(ADP rank): one per position (fallback: all)
    picks = [p for p in draft.get("draftDetail", {}).get("picks", []) if not p.get("keeper")]
    all_pairs = []
    pos_pairs = defaultdict(list)
    # positional ADP rank among drafted players of that position
    by_pos_adp = defaultdict(list)
    for p in picks:
        pid = p["playerId"]
        a = adp.get(pid, p["overallPickNumber"])
        by_pos_adp[pos_of.get(pid)].append((a, pid))
    pos_rank = {}
    for pos, lst in by_pos_adp.items():
        for i, (_a, pid) in enumerate(sorted(lst), 1):
            pos_rank[pid] = i
    for p in picks:
        pid = p["playerId"]
        a = adp.get(pid, p["overallPickNumber"])
        y = kona_season_pts.get(pid, 0.0)
        all_pairs.append((math.log(a), y))
        pos = pos_of.get(pid)
        if pos is not None:
            pos_pairs[pos].append((math.log(pos_rank[pid]), y))
    b0, b1 = fit_loglinear(all_pairs)
    pos_fits = {pos: fit_loglinear(pairs)
                for pos, pairs in pos_pairs.items() if len(pairs) >= 8}

    def expected_pick_points(pid, fallback_adp):
        pos = pos_of.get(pid)
        if pos in pos_fits and pid in pos_rank:
            pb0, pb1 = pos_fits[pos]
            return pb0 + pb1 * math.log(pos_rank[pid])
        a = adp.get(pid, fallback_adp)
        return b0 + b1 * math.log(a)

    def adp_expected_ppg(pid):
        a = adp.get(pid)
        if not a:
            return 0.0
        return max(0.0, (b0 + b1 * math.log(a)) / n_weeks)

    def ppg(pid):
        v = list(player_week_pts.get(pid, {}).values())
        if len(v) >= 2:
            return statistics.mean(v)
        # little or no sample: lean on ADP expectation
        return max(statistics.mean(v) if v else 0.0, adp_expected_ppg(pid))

    # user-maintained overrides: absences that are not injuries
    ov_path = ROOT / "data" / "overrides.json"
    overrides = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
    non_injury = {}  # name -> set of weeks (empty set = all weeks)
    for o in overrides.get("nonInjuryAbsences", []):
        non_injury[o["player"]] = set(o.get("weeks", []))

    def is_non_injury(name, wk):
        w = non_injury.get(name)
        return w is not None and (not w or wk in w)

    injury_lost = defaultdict(float)
    injury_weeks = defaultdict(int)
    injury_detail = defaultdict(list)
    for wk, by_team in rosters.items():
        for t, rows in by_team.items():
            for pid, slot, played, pro_team, pts, _elig in rows:
                name = player_names.get(pid, str(pid))
                if byes.get(pro_team) == wk or is_non_injury(name, wk):
                    continue
                slot_lbl = "IR" if slot == IR_SLOT else ("BE" if slot == BENCH_SLOT else "ST")
                if not played:
                    lost = ppg(pid)
                    injury_weeks[t] += 1
                    if lost > 0:
                        injury_lost[t] += lost
                        injury_detail[t].append({
                            "week": wk, "player": name, "slot": slot_lbl,
                            "lostPpg": round(lost, 1), "type": "missed",
                        })
                else:
                    # mid-game injury: played but got hurt and hasn't played since
                    # (and it wasn't just the most recent completed week).
                    later = [w for w in player_week_pts.get(pid, {}) if w > wk]
                    last_wk = max(player_week_pts.get(pid, {}), default=None)
                    if (not later and last_wk == wk and wk < n_weeks):
                        healthy = [v for w, v in player_week_pts[pid].items() if w != wk]
                        if len(healthy) >= 2:
                            avg = statistics.mean(healthy)
                            gap = avg - pts
                            if gap > max(5.0, 0.5 * avg):
                                injury_lost[t] += gap
                                injury_weeks[t] += 1
                                injury_detail[t].append({
                                    "week": wk, "player": name, "slot": slot_lbl,
                                    "lostPpg": round(gap, 1), "type": "mid-game",
                                })

    # Season-ending injuries keep counting after the player is dropped:
    # if a player's LAST week on a team was injury-flagged (missed or
    # mid-game exit), he never plays again, his current status is IR/OUT,
    # and no team rosters him afterward, the original team eats his PPG
    # for every completed week after the drop.
    current_status = {}
    for p in players_raw.get("players", []):
        current_status[p["player"]["id"]] = p["player"].get("injuryStatus")
    rostered_by = defaultdict(set)   # pid -> set of weeks rostered (any team)
    team_weeks = defaultdict(dict)   # pid -> week -> (team, played, pts)
    for wk, by_team in rosters.items():
        for t, rows in by_team.items():
            for pid, slot, played, pro_team, pts, _elig in rows:
                rostered_by[pid].add(wk)
                team_weeks[pid][wk] = (t, played, pts)
    for pid, wkmap in team_weeks.items():
        name = player_names.get(pid, str(pid))
        if name in non_injury:
            continue
        last_wk = max(wkmap)
        if last_wk >= n_weeks:
            continue  # still rostered through latest week
        t, played_last, pts_last = wkmap[last_wk]
        if current_status.get(pid) not in ("INJURY_RESERVE", "OUT"):
            continue
        last_played = max(player_week_pts.get(pid, {}), default=None)
        if last_played is not None and last_played > last_wk:
            continue  # played after leaving the roster: not season-ended then
        # last rostered week must look like the injury (didn't play, or
        # mid-game exit well below his average)
        healthy = [v for w, v in player_week_pts.get(pid, {}).items()
                   if not (w == last_wk and played_last)]
        avg = statistics.mean(healthy) if len(healthy) >= 2 else ppg(pid)
        injury_flagged = (not played_last) or (avg - pts_last > max(5.0, 0.5 * avg))
        if not injury_flagged or avg <= 0:
            continue
        for wk in range(last_wk + 1, n_weeks + 1):
            if wk in rostered_by[pid]:
                break  # someone picked him up; stop crediting
            injury_lost[t] += avg
            injury_weeks[t] += 1
            injury_detail[t].append({
                "week": wk, "player": name, "slot": "--",
                "lostPpg": round(avg, 1), "type": "post-drop",
            })

    # ---- Regret Index: dropped players who produced elsewhere --------------
    # Departures from a roster, excluding trades (data/trades.json is
    # authoritative; reciprocal same-week roster swaps are auto-detected as a
    # fallback). Regret = points the player scored after leaving.
    trades_path = ROOT / "data" / "trades.json"
    traded_away = set()  # (player name, teamId, week)
    manual_pairs = set()  # (week, frozenset of teamIds) listed in trades.json
    name_to_tid = {v.strip(): k for k, v in team_names.items()}
    if trades_path.exists():
        for tr in json.loads(trades_path.read_text(encoding="utf-8")).get("trades", []):
            pair = frozenset(name_to_tid.get(tm.strip()) for tm in tr["teams"])
            manual_pairs.add((tr["week"], pair))
            for pname, dest in tr.get("players", {}).items():
                for tm in tr["teams"]:
                    if tm.strip() != dest.strip():
                        tid = name_to_tid.get(tm.strip())
                        if tid is not None:
                            traded_away.add((pname, tid, tr["week"]))

    on_team_wk = defaultdict(dict)  # pid -> week -> teamId
    for wk, by_team in rosters.items():
        for t, rows in by_team.items():
            for pid, _slot, _played, _pro, _pts, _elig in rows:
                on_team_wk[pid][wk] = t
    # reciprocal swap detection (fallback trade detection)
    moves = defaultdict(set)
    for pid, h in on_team_wk.items():
        for w in sorted(h):
            if w + 1 in h and h[w + 1] != h[w]:
                moves[(w, h[w], h[w + 1])].add(pid)
    auto_traded = set()
    for (w, a, b), pids in moves.items():
        if (w, frozenset((a, b))) in manual_pairs:
            continue  # trades.json is authoritative for this pair/week
        if moves.get((w, b, a)):
            for pid in pids:
                auto_traded.add((pid, a, w))

    # weakest starter points by (week, team, position) — the slot a dropped
    # player would plausibly have filled
    POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
    min_starter = {}
    for wk, by_team in rosters.items():
        for t, rows in by_team.items():
            for pid, slot, played, _pro, pts, _elig in rows:
                if slot in (BENCH_SLOT, IR_SLOT):
                    continue
                pos = pos_of.get(pid)
                key = (wk, t, pos)
                if key not in min_starter or pts < min_starter[key]:
                    min_starter[key] = pts

    regret = defaultdict(float)
    net_regret = defaultdict(float)
    regret_detail = defaultdict(list)
    for pid, h in on_team_wk.items():
        wks = sorted(h)
        name = player_names.get(pid, str(pid))
        for w in wks:
            t = h[w]
            if w == n_weeks or h.get(w + 1) == t:
                continue
            if any(h.get(x) == t for x in range(w + 1, n_weeks + 1)):
                continue  # came back to the same team
            if (name, t, w) in traded_away or (pid, t, w) in auto_traded:
                continue
            pos = pos_of.get(pid)
            total = net = 0.0
            games = 0
            for x in range(w + 1, n_weeks + 1):
                p = player_week_pts.get(pid, {}).get(x)
                if p is None:
                    continue
                games += 1
                total += p
                net += max(0.0, p - min_starter.get((x, t, pos), 0.0))
            if total > 0:
                regret[t] += total
                net_regret[t] += net
                regret_detail[t].append({
                    "player": name, "pos": POS.get(pos, "?"), "droppedAfterWeek": w,
                    "pointsSince": round(total, 1), "gamesSince": games,
                    "ppgSince": round(total / games, 1) if games else 0.0,
                    "netRegret": round(net, 1),
                })
    for t in regret_detail:
        regret_detail[t].sort(key=lambda d: -d["netRegret"])

    # ---- draft luck vs ADP ------------------------------------------------
    # Team draft luck = sum over non-keeper picks of (actual season points -
    # points expected at that player's ADP, from the fit above).
    draft_luck = defaultdict(float)
    draft_detail = defaultdict(list)
    for p in picks:
        pid = p["playerId"]
        a = adp.get(pid, p["overallPickNumber"])
        exp = expected_pick_points(pid, p["overallPickNumber"])
        act = kona_season_pts.get(pid, 0.0)
        resid = act - exp
        t = p["teamId"]
        draft_luck[t] += resid
        draft_detail[t].append({
            "player": player_names.get(pid, str(pid)), "pick": p["overallPickNumber"],
            "adp": round(a, 1), "expected": round(exp, 1), "actual": round(act, 1),
            "residual": round(resid, 1),
        })
    for t in draft_detail:
        draft_detail[t].sort(key=lambda d: d["residual"])

    # ---- manager efficiency: actual vs optimal lineup ----------------------
    slot_counts = {int(k): v for k, v in
                   core["settings"]["rosterSettings"]["lineupSlotCounts"].items()
                   if v > 0 and int(k) not in (BENCH_SLOT, IR_SLOT)}

    def optimal_points(rows):
        """Greedy over slots, most-restrictive first, FLEX-style slots last."""
        avail = [(pts, pid, set(elig)) for pid, _s, _p, _pro, pts, elig in rows]
        order = sorted(
            (s for s, c in slot_counts.items() for _ in range(c)),
            key=lambda s: sum(1 for _, _, e in avail if s in e))
        total = 0.0
        used = set()
        for s in order:
            best = max(((pts, pid) for pts, pid, e in avail
                        if s in e and pid not in used), default=None)
            if best:
                total += best[0]
                used.add(best[1])
        return total

    eff_actual = defaultdict(float)
    eff_optimal = defaultdict(float)
    for wk, by_team in rosters.items():
        for t, rows in by_team.items():
            eff_actual[t] += sum(pts for _pid, s, _p, _pro, pts, _e in rows
                                 if s not in (BENCH_SLOT, IR_SLOT))
            eff_optimal[t] += optimal_points(rows)

    # ---- waiver heroes: production from undrafted, untraded pickups --------
    drafted_by = {}
    for p in draft.get("draftDetail", {}).get("picks", []):
        drafted_by[p["playerId"]] = p["teamId"]
    traded_to = set()  # (player name, destination teamId)
    if trades_path.exists():
        for tr in json.loads(trades_path.read_text(encoding="utf-8")).get("trades", []):
            for pname, dest in tr.get("players", {}).items():
                tid = name_to_tid.get(dest.strip())
                if tid is not None:
                    traded_to.add((pname, tid))
    waiver_pts = defaultdict(float)
    waiver_by_player = defaultdict(lambda: defaultdict(float))
    for wk, by_team in rosters.items():
        for t, rows in by_team.items():
            for pid, slot, _p, _pro, pts, _e in rows:
                if slot in (BENCH_SLOT, IR_SLOT) or pts <= 0:
                    continue
                name = player_names.get(pid, str(pid))
                if drafted_by.get(pid) == t or (name, t) in traded_to:
                    continue
                waiver_pts[t] += pts
                waiver_by_player[t][name] += pts
    waiver_detail = {
        t: [{"player": n, "points": round(v, 1)}
            for n, v in sorted(d.items(), key=lambda kv: -kv[1])[:6]]
        for t, d in waiver_by_player.items()}

    # ---- trade desk: points banked by each side since the deal -------------
    trade_desk = []
    if trades_path.exists():
        for tr in json.loads(trades_path.read_text(encoding="utf-8")).get("trades", []):
            sides = defaultdict(list)
            for pname, dest in tr.get("players", {}).items():
                tid = name_to_tid.get(dest.strip())
                pid = next((k for k, v in player_names.items() if v == pname), None)
                started = total = 0.0
                if pid is not None and tid is not None:
                    for wk in range(tr["week"] + 1, n_weeks + 1):
                        row = next((r for r in rosters.get(wk, {}).get(tid, [])
                                    if r[0] == pid), None)
                        if row:
                            total += row[4]
                            if row[1] not in (BENCH_SLOT, IR_SLOT):
                                started += row[4]
                sides[dest.strip()].append(
                    {"player": pname, "totalSince": round(total, 1),
                     "startedSince": round(started, 1)})
            trade_desk.append({
                "week": tr["week"],
                "sides": [{"team": team, "received": players,
                           "startedTotal": round(sum(p["startedSince"] for p in players), 1)}
                          for team, players in sides.items()],
            })

    # ---- record book -------------------------------------------------------
    all_scores = [(scores[wk][t], t, wk) for wk in completed_weeks for t in scores[wk]]
    games = []
    for wk in completed_weeks:
        done = set()
        for t in scores[wk]:
            o = opponents[wk][t]
            if (o, t) in done:
                continue
            done.add((t, o))
            a, b = scores[wk][t], scores[wk][o]
            w_t, l_t = (t, o) if a > b else (o, t)
            games.append({"week": wk, "winner": w_t, "loser": l_t,
                          "winPts": round(max(a, b), 1), "losePts": round(min(a, b), 1),
                          "margin": round(abs(a - b), 1)})
    record_book = {
        "highScores": [{"points": round(p, 1), "teamId": t, "week": w}
                       for p, t, w in sorted(all_scores, reverse=True)[:5]],
        "lowScores": [{"points": round(p, 1), "teamId": t, "week": w}
                      for p, t, w in sorted(all_scores)[:5]],
        "biggestBlowout": max(games, key=lambda g: g["margin"]),
        "narrowestWin": min(games, key=lambda g: g["margin"]),
        "bestLoss": max(games, key=lambda g: g["losePts"]),
        "worstWin": min(games, key=lambda g: g["winPts"]),
    }

    # ---- components & composite ------------------------------------------
    sched_comp = {t: h2h_wins[t] - allplay_wins[t] for t in team_ids}
    close_comp = {t: close_w[t] - (close_w[t] + close_l[t]) / 2 for t in team_ids}
    pa_avg = statistics.mean(pa[t] for t in team_ids)
    pa_comp = {t: pa_avg - pa[t] for t in team_ids}  # positive = faced fewer pts = lucky
    inj_avg = statistics.mean(injury_lost[t] for t in team_ids)
    inj_comp = {t: inj_avg - injury_lost[t] for t in team_ids}  # positive = healthier = lucky
    draft_comp = {t: draft_luck[t] for t in team_ids}

    z = {name: zscores(comp) for name, comp in [
        ("schedule", sched_comp), ("close", close_comp), ("pa", pa_comp),
        ("injury", inj_comp), ("draft", draft_comp)]}
    luck_index = {
        t: sum(WEIGHTS[k] * z[k][t] for k in WEIGHTS) for t in team_ids
    }
    # scale to a friendly -100..100-ish range
    luck_scaled = {t: round(v * 100, 1) for t, v in luck_index.items()}

    # expected record: all-play win% applied to H2H games + actual median wins
    xwins = {t: allplay_wins[t] + median_wins[t] for t in team_ids}

    out = {
        "season": season,
        "league": core["settings"]["name"],
        "generatedWeekThrough": max(completed_weeks),
        "closeGameMargin": CLOSE_GAME_MARGIN,
        "weights": WEIGHTS,
        "teams": [],
        "weekly": [
            {"week": w, "teamId": t, "points": pts, "oppId": o, "oppPoints": op,
             "won": bool(wn), "beatMedian": bool(bm), "allPlayPct": round(ap_, 3)}
            for (_, w, t, pts, o, op, wn, bm, ap_) in weekly_rows
        ],
        "luckiestWins": sorted(luckiest_wins, key=lambda d: -d["rank"])[:10],
        "toughestLosses": sorted(toughest_losses, key=lambda d: d["rank"])[:10],
        "tradeDesk": trade_desk,
        "recordBook": record_book,
    }
    for t in team_ids:
        rec = teams[t]["record"]["overall"]
        starter_pts = pf[t]
        out["teams"].append({
            "teamId": t,
            "name": team_names[t],
            "abbrev": abbrevs[t],
            "wins": rec["wins"], "losses": rec["losses"],
            "h2hWins": h2h_wins[t], "h2hLosses": n_weeks - h2h_wins[t],
            "medianWins": median_wins[t],
            "pointsFor": round(pf[t], 1), "pointsAgainst": round(pa[t], 1),
            "allPlayWins": round(allplay_wins[t], 2),
            "xWins": round(xwins[t], 2),
            "winsVsExpected": round((h2h_wins[t] + median_wins[t]) - xwins[t], 2),
            "closeWins": close_w[t], "closeLosses": close_l[t],
            "topScoreWeeks": top_score_weeks[t],
            "injuryPointsLost": round(injury_lost[t], 1),
            "injuryPlayerWeeks": injury_weeks[t],
            "injuryDetail": sorted(injury_detail[t], key=lambda d: -d["lostPpg"])[:40],
            "regretPoints": round(regret[t], 1),
            "netRegretPoints": round(net_regret[t], 1),
            "lineupPoints": round(eff_actual[t], 1),
            "optimalPoints": round(eff_optimal[t], 1),
            "efficiency": round(eff_actual[t] / eff_optimal[t], 3) if eff_optimal[t] else 0.0,
            "benchPointsLeft": round(eff_optimal[t] - eff_actual[t], 1),
            "waiverPoints": round(waiver_pts[t], 1),
            "waiverDetail": waiver_detail.get(t, []),
            "scoreStdev": round(statistics.pstdev([scores[w][t] for w in completed_weeks]), 1),
            "regretDetail": regret_detail[t][:8],
            "draftLuckPoints": round(draft_luck[t], 1),
            "draftDetail": draft_detail[t][:5] + draft_detail[t][-3:][::-1] if draft_detail[t] else [],
            "components": {k: round(z[k][t], 2) for k in WEIGHTS},
            "luckIndex": luck_scaled[t],
        })
    out["teams"].sort(key=lambda d: -d["luckIndex"])

    if not args.through:
        (ROOT / "data" / f"metrics_{season}.json").write_text(
            json.dumps(out, indent=1), encoding="utf-8")

    # ---- history db --------------------------------------------------------
    db = sqlite3.connect(ROOT / "data" / "league.db")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS teams(season INT, team_id INT, name TEXT, abbrev TEXT,
        PRIMARY KEY(season, team_id));
    CREATE TABLE IF NOT EXISTS weekly_results(season INT, week INT, team_id INT,
        points REAL, opp_id INT, opp_points REAL, won INT, beat_median INT,
        all_play_pct REAL, PRIMARY KEY(season, week, team_id));
    CREATE TABLE IF NOT EXISTS luck_snapshots(season INT, through_week INT, team_id INT,
        luck_index REAL, z_schedule REAL, z_close REAL, z_pa REAL, z_injury REAL,
        z_draft REAL, injury_pts_lost REAL, draft_luck_pts REAL,
        PRIMARY KEY(season, through_week, team_id));
    """)
    db.executemany("INSERT OR REPLACE INTO teams VALUES(?,?,?,?)",
                   [(season, t, team_names[t], abbrevs[t]) for t in team_ids])
    db.executemany("INSERT OR REPLACE INTO weekly_results VALUES(?,?,?,?,?,?,?,?,?)",
                   weekly_rows)
    thru = max(completed_weeks)
    db.executemany("INSERT OR REPLACE INTO luck_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   [(season, thru, t, luck_scaled[t], z["schedule"][t], z["close"][t],
                     z["pa"][t], z["injury"][t], z["draft"][t],
                     round(injury_lost[t], 1), round(draft_luck[t], 1)) for t in team_ids])
    db.commit()
    db.close()

    if args.through:
        print(f"snapshot backfilled through week {thru}")
        return
    print(f"metrics written through week {thru}")
    for te in out["teams"]:
        print(f"{te['luckIndex']:>7}  {te['name']:<28} {te['wins']}-{te['losses']}  "
              f"xW {te['xWins']}  inj -{te['injuryPointsLost']}  draft {te['draftLuckPoints']:+}")


if __name__ == "__main__":
    main()
