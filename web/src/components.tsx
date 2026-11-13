import type { LeagueData } from "./types";
import { analystTake, fmt, powerRankings, signed, teamName, valClass } from "./util";

/* ---------- shared bits ---------- */

export function LuckBar({ value, max }: { value: number; max: number }) {
  const pct = Math.min(Math.abs(value) / max, 1) * 50;
  const pos = value >= 0;
  return (
    <div className="lbar">
      <div className="track">
        <div className="mid" />
        <div
          className={"fill" + (pos ? "" : " neg")}
          style={{
            width: `${pct}%`,
            left: pos ? "50%" : `${50 - pct}%`,
            background: pos ? "var(--lucky)" : "var(--unlucky)",
          }}
        />
      </div>
      <span className={valClass(value)} style={{ width: 52, textAlign: "right" }}>
        {signed(value)}
      </span>
    </div>
  );
}

function ZCell({ z }: { z: number }) {
  return <td className={"num " + valClass(z)}>{signed(z, 2)}</td>;
}

/* ---------- segments ---------- */

export function BigBoard({ data }: { data: LeagueData }) {
  const max = Math.max(...data.teams.map((t) => Math.abs(t.luckIndex)));
  return (
    <>
      <h2 className="segment-title">The Big Board</h2>
      <p className="segment-sub">
        The Luck Index: five components of fortune, z-scored and weighted. Positive =
        the football gods owe you nothing. Negative = file a grievance.
      </p>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th></th><th>Team</th><th className="num">Record</th>
              <th className="num">xW</th><th>Luck Index</th>
            </tr>
          </thead>
          <tbody>
            {data.teams.map((t, i) => (
              <tr key={t.teamId}>
                <td><span className="rank">{i + 1}</span></td>
                <td>
                  <div className="team-cell">
                    {t.name.trim()}
                    {i === 0 && <span className="badge gold">LEAGUE'S LUCKIEST</span>}
                    {i === data.teams.length - 1 && <span className="badge hot">SOB STORY</span>}
                  </div>
                  <div className="sub">{analystTake(t)}</div>
                </td>
                <td className="num">{t.wins}-{t.losses}</td>
                <td className="num">{fmt(t.xWins, 1)}</td>
                <td><LuckBar value={t.luckIndex} max={max} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function ComponentCenter({ data }: { data: LeagueData }) {
  const w = data.weights as Record<string, number>;
  return (
    <>
      <h2 className="segment-title">Component Center</h2>
      <p className="segment-sub">
        Every ingredient of the Luck Index, per team. Each column is a league z-score;
        weights: schedule {w.schedule * 100}%, injury {w.injury * 100}%, close {w.close * 100}%,
        points-against {w.pa * 100}%, draft {w.draft * 100}%.
      </p>
      <div className="card" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Team</th><th className="num">Luck</th>
              <th className="num">Schedule</th><th className="num">Close</th>
              <th className="num">Pts Agst</th><th className="num">Injury</th>
              <th className="num">Draft</th><th className="num">Close W-L</th>
              <th className="num">PA</th><th className="num">Inj Lost</th>
              <th className="num">Draft ±</th>
            </tr>
          </thead>
          <tbody>
            {data.teams.map((t) => (
              <tr key={t.teamId}>
                <td className="team-cell">{t.name.trim()}</td>
                <td className={"num " + valClass(t.luckIndex)}>{signed(t.luckIndex)}</td>
                <ZCell z={t.components.schedule} />
                <ZCell z={t.components.close} />
                <ZCell z={t.components.pa} />
                <ZCell z={t.components.injury} />
                <ZCell z={t.components.draft} />
                <td className="num">{t.closeWins}-{t.closeLosses}</td>
                <td className="num">{fmt(t.pointsAgainst, 0)}</td>
                <td className="num">{fmt(t.injuryPointsLost, 0)}</td>
                <td className="num">{signed(t.draftLuckPoints, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function PowerCenter({ data }: { data: LeagueData }) {
  const ranks = powerRankings(data.teams);
  const standings = [...data.teams].sort(
    (a, b) => b.wins - a.wins || b.pointsFor - a.pointsFor);
  const standingOf = new Map(standings.map((t, i) => [t.teamId, i + 1]));
  return (
    <>
      <h2 className="segment-title">Power Rankings</h2>
      <p className="segment-sub">
        The luck-free truth: 60% all-play record, 40% scoring. Δ = spots vs the actual
        standings — big positive numbers mean the standings are lying about you.
      </p>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th></th><th>Team</th><th className="num">All-Play W</th>
              <th className="num">PF</th><th className="num">Consistency</th>
              <th className="num">Standings</th><th className="num">Δ</th>
            </tr>
          </thead>
          <tbody>
            {ranks.map(({ team: t }, i) => {
              const d = (standingOf.get(t.teamId) ?? 0) - (i + 1);
              return (
                <tr key={t.teamId}>
                  <td><span className="rank">{i + 1}</span></td>
                  <td className="team-cell">{t.name.trim()}</td>
                  <td className="num">{fmt(t.allPlayWins, 1)}</td>
                  <td className="num">{fmt(t.pointsFor, 0)}</td>
                  <td className="num">{fmt(t.scoreStdev, 1)}</td>
                  <td className="num">#{standingOf.get(t.teamId)}</td>
                  <td className={"num " + valClass(d)}>{d === 0 ? "—" : signed(d, 0)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function CoachingReport({ data }: { data: LeagueData }) {
  const sorted = [...data.teams].sort((a, b) => b.efficiency - a.efficiency);
  return (
    <>
      <h2 className="segment-title">Coaching Report</h2>
      <p className="segment-sub">
        Lineup efficiency: points started vs the perfect-hindsight lineup. This is the
        skill column — the Luck Index measures what happened to you; this measures
        what you did about it.
      </p>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th></th><th>Team</th><th className="num">Started</th>
              <th className="num">Optimal</th><th className="num">Left on Bench</th>
              <th className="num">Efficiency</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((t, i) => (
              <tr key={t.teamId}>
                <td><span className="rank">{i + 1}</span></td>
                <td>
                  <div className="team-cell">
                    {t.name.trim()}
                    {i === 0 && <span className="badge gold">COACH OF THE YEAR</span>}
                    {i === sorted.length - 1 && <span className="badge hot">PRESS CONFERENCE PENDING</span>}
                  </div>
                </td>
                <td className="num">{fmt(t.lineupPoints, 0)}</td>
                <td className="num">{fmt(t.optimalPoints, 0)}</td>
                <td className="num val-neg">{fmt(t.benchPointsLeft, 1)}</td>
                <td className="num" style={{ fontWeight: 700 }}>{fmt(t.efficiency * 100, 1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function Transactions({ data }: { data: LeagueData }) {
  const regret = [...data.teams].sort((a, b) => b.netRegretPoints - a.netRegretPoints);
  const waiver = [...data.teams].sort((a, b) => b.waiverPoints - a.waiverPoints);
  return (
    <>
      <h2 className="segment-title">Transaction Wire</h2>
      <p className="segment-sub">
        The Regret Index (points your drops scored elsewhere — net is measured against
        what you started instead) and the Waiver Heroes who balance the ledger.
      </p>
      <div className="grid-2">
        <div className="card">
          <h3>Not Top 10: The Ones That Got Away</h3>
          <table>
            <thead>
              <tr><th>Team</th><th className="num">Raw</th><th className="num">Net</th><th>Biggest Regret</th></tr>
            </thead>
            <tbody>
              {regret.map((t) => {
                const top = t.regretDetail[0];
                return (
                  <tr key={t.teamId}>
                    <td className="team-cell">{t.name.trim()}</td>
                    <td className="num">{fmt(t.regretPoints, 0)}</td>
                    <td className="num val-neg">{fmt(t.netRegretPoints, 0)}</td>
                    <td className="sub">
                      {top ? `${top.player} — ${fmt(top.pointsSince, 0)} pts since wk${top.droppedAfterWeek}` : "clean hands"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3>Waiver Heroes</h3>
          <table>
            <thead>
              <tr><th>Team</th><th className="num">Pickup Pts Started</th><th>Headliners</th></tr>
            </thead>
            <tbody>
              {waiver.map((t) => (
                <tr key={t.teamId}>
                  <td className="team-cell">{t.name.trim()}</td>
                  <td className="num val-pos">{fmt(t.waiverPoints, 0)}</td>
                  <td className="sub">
                    {t.waiverDetail.slice(0, 2).map((d) => `${d.player} (${fmt(d.points, 0)})`).join(", ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export function TradeDesk({ data }: { data: LeagueData }) {
  return (
    <>
      <h2 className="segment-title">Trade Desk</h2>
      <p className="segment-sub">
        Every consummated deal, graded live: points each side's haul has actually
        started since the trade. Scoreboard never lies.
      </p>
      {data.tradeDesk.length === 0 && (
        <div className="card">No trades yet. Cowards.</div>
      )}
      {data.tradeDesk.map((tr, i) => {
        const best = Math.max(...tr.sides.map((s) => s.startedTotal));
        return (
          <div className="card" key={i}>
            <h3>Week {tr.week} Deal</h3>
            <div className="grid-2">
              {tr.sides.map((s) => (
                <div key={s.team}>
                  <div className="team-cell">
                    {s.team}
                    {s.startedTotal === best && <span className="badge gold">WINNING THE TRADE</span>}
                  </div>
                  <table>
                    <tbody>
                      {s.received.map((p) => (
                        <tr key={p.player}>
                          <td>{p.player}</td>
                          <td className="num">{fmt(p.startedSince, 1)} started</td>
                          <td className="num sub">{fmt(p.totalSince, 1)} total</td>
                        </tr>
                      ))}
                      <tr>
                        <td style={{ fontWeight: 700 }}>Side total</td>
                        <td className="num" style={{ fontWeight: 700 }}>{fmt(s.startedTotal, 1)}</td>
                        <td />
                      </tr>
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </>
  );
}

export function InjuryReport({ data }: { data: LeagueData }) {
  const sorted = [...data.teams].sort((a, b) => b.injuryPointsLost - a.injuryPointsLost);
  return (
    <>
      <h2 className="segment-title">The Injury Report</h2>
      <p className="segment-sub">
        Starter-value points lost to players who missed games — including mid-game
        exits and season-enders that kept counting after the drop. Suspensions and
        legal absences excluded by league ruling.
      </p>
      {sorted.map((t, i) => (
        <div className="card" key={t.teamId}>
          <h3>
            {i + 1}. {t.name.trim()} — <span className="val-neg">−{fmt(t.injuryPointsLost, 1)} pts</span>
            <span className="sub"> over {t.injuryPlayerWeeks} player-weeks</span>
            {i === 0 && <span className="badge hot">MASH UNIT OF THE YEAR</span>}
          </h3>
          <table>
            <thead>
              <tr><th>Week</th><th>Player</th><th>Status</th><th className="num">Value Lost</th></tr>
            </thead>
            <tbody>
              {t.injuryDetail.slice(0, 10).map((d, j) => (
                <tr key={j}>
                  <td>Wk {d.week}</td>
                  <td>{d.player}</td>
                  <td className="sub">
                    {d.type === "post-drop" ? "season-ender (post-drop)" :
                     d.type === "mid-game" ? "left mid-game" :
                     d.slot === "IR" ? "IR" : d.slot === "BE" ? "benched, out" : "started, out"}
                  </td>
                  <td className="num val-neg">−{fmt(d.lostPpg, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}

export function RecordBook({ data }: { data: LeagueData }) {
  const rb = data.recordBook;
  const tn = (id?: number) => (id != null ? teamName(data, id) : "?");
  const game = (g: { week: number; winner?: number; loser?: number; winPts?: number; losePts?: number }) =>
    `${tn(g.winner)} ${fmt(g.winPts ?? 0, 1)} — ${fmt(g.losePts ?? 0, 1)} ${tn(g.loser)} (wk ${g.week})`;
  return (
    <>
      <h2 className="segment-title">Record Book</h2>
      <p className="segment-sub">Season {data.season}, through week {data.generatedWeekThrough}.</p>
      <div className="grid-2">
        <div className="card">
          <h3>Highest Scores</h3>
          <table><tbody>
            {rb.highScores.map((g, i) => (
              <tr key={i}>
                <td><span className="rank">{i + 1}</span>{tn(g.teamId)}</td>
                <td className="sub">wk {g.week}</td>
                <td className="num val-pos">{fmt(g.points ?? 0, 1)}</td>
              </tr>
            ))}
          </tbody></table>
        </div>
        <div className="card">
          <h3>Lowest Scores</h3>
          <table><tbody>
            {rb.lowScores.map((g, i) => (
              <tr key={i}>
                <td><span className="rank">{i + 1}</span>{tn(g.teamId)}</td>
                <td className="sub">wk {g.week}</td>
                <td className="num val-neg">{fmt(g.points ?? 0, 1)}</td>
              </tr>
            ))}
          </tbody></table>
        </div>
      </div>
      <div className="card">
        <h3>One-Liners</h3>
        <div className="take"><b>Biggest blowout:</b> {game(rb.biggestBlowout)} — margin {fmt(rb.biggestBlowout.margin ?? 0, 1)}</div>
        <div className="take"><b>Narrowest win:</b> {game(rb.narrowestWin)} — margin {fmt(rb.narrowestWin.margin ?? 0, 1)}</div>
        <div className="take"><b>Best score to still lose:</b> {game(rb.bestLoss)}</div>
        <div className="take"><b>Worst score to still win:</b> {game(rb.worstWin)}</div>
      </div>
    </>
  );
}
