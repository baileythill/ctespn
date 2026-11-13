export interface InjuryRow {
  week: number; player: string; slot: string; lostPpg: number; type?: string;
}
export interface DraftRow {
  player: string; pick: number; adp: number; expected: number; actual: number; residual: number;
}
export interface RegretRow {
  player: string; pos: string; droppedAfterWeek: number;
  pointsSince: number; gamesSince: number; ppgSince: number; netRegret: number;
}
export interface Team {
  teamId: number; name: string; abbrev: string;
  wins: number; losses: number; h2hWins: number; h2hLosses: number; medianWins: number;
  pointsFor: number; pointsAgainst: number;
  allPlayWins: number; xWins: number; winsVsExpected: number;
  closeWins: number; closeLosses: number; topScoreWeeks: number;
  injuryPointsLost: number; injuryPlayerWeeks: number; injuryDetail: InjuryRow[];
  draftLuckPoints: number; draftDetail: DraftRow[];
  regretPoints: number; netRegretPoints: number; regretDetail: RegretRow[];
  lineupPoints: number; optimalPoints: number; efficiency: number; benchPointsLeft: number;
  waiverPoints: number; waiverDetail: { player: string; points: number }[];
  scoreStdev: number;
  components: { schedule: number; close: number; pa: number; injury: number; draft: number };
  luckIndex: number;
}
export interface WeeklyRow {
  week: number; teamId: number; points: number; oppId: number; oppPoints: number;
  won: boolean; beatMedian: boolean; allPlayPct: number;
}
export interface GameRef {
  week: number; winner?: number; loser?: number; teamId?: number;
  winPts?: number; losePts?: number; margin?: number; points?: number;
  oppPoints?: number; rank?: number;
}
export interface TradeSide {
  team: string; received: { player: string; totalSince: number; startedSince: number }[];
  startedTotal: number;
}
export interface LeagueData {
  season: number; league: string; generatedWeekThrough: number;
  closeGameMargin: number;
  weights: Record<string, number>;
  teams: Team[];
  weekly: WeeklyRow[];
  luckiestWins: GameRef[];
  toughestLosses: GameRef[];
  tradeDesk: { week: number; sides: TradeSide[] }[];
  recordBook: {
    highScores: GameRef[]; lowScores: GameRef[];
    biggestBlowout: GameRef; narrowestWin: GameRef; bestLoss: GameRef; worstWin: GameRef;
  };
  luckTrend: { week: number; teamId: number; luck: number }[];
}
