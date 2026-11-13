import type { LeagueData, Team } from "./types";

export const fmt = (n: number, d = 1) =>
  n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

export const signed = (n: number, d = 1) => (n > 0 ? "+" : "") + fmt(n, d);

export function teamName(data: LeagueData, id: number): string {
  return data.teams.find((t) => t.teamId === id)?.name.trim() ?? `Team ${id}`;
}

export function valClass(n: number): string {
  if (n > 0.001) return "val-pos";
  if (n < -0.001) return "val-neg";
  return "val-zero";
}

/** Power score: luck-stripped quality = all-play rate + scoring, z-combined. */
export function powerRankings(teams: Team[]): { team: Team; score: number }[] {
  const z = (vals: number[]) => {
    const m = vals.reduce((a, b) => a + b, 0) / vals.length;
    const sd = Math.sqrt(vals.reduce((a, b) => a + (b - m) ** 2, 0) / vals.length) || 1;
    return vals.map((v) => (v - m) / sd);
  };
  const ap = z(teams.map((t) => t.allPlayWins));
  const pf = z(teams.map((t) => t.pointsFor));
  return teams
    .map((team, i) => ({ team, score: 0.6 * ap[i] + 0.4 * pf[i] }))
    .sort((a, b) => b.score - a.score);
}

/** One-line studio take per team, from its most extreme component. */
export function analystTake(t: Team): string {
  const c = t.components;
  const entries: [string, number, string, string][] = [
    ["schedule", c.schedule,
      "has been winning games their scores didn't earn",
      "keeps outscoring the league and losing anyway"],
    ["close", c.close,
      `is living right in close games (${t.closeWins}-${t.closeLosses} in one-score finishes)`,
      `can't buy a coin flip (${t.closeWins}-${t.closeLosses} in one-score finishes)`],
    ["pa", c.pa,
      "keeps catching opponents on their bye-week energy",
      "faces the league's buzzsaw schedule week after week"],
    ["injury", c.injury,
      "has the league's training staff of the year",
      `runs a MASH unit (${fmt(t.injuryPointsLost, 0)} points lost to injury)`],
    ["draft", c.draft,
      "drafted like they saw the future",
      "drafted a list of cautionary tales"],
  ];
  const worst = entries.reduce((a, b) => (Math.abs(b[1]) > Math.abs(a[1]) ? b : a));
  return worst[1] >= 0 ? worst[2] : worst[3];
}
