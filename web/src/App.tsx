import { useEffect, useMemo, useState } from "react";
import type { LeagueData } from "./types";
import {
  BigBoard, CoachingReport, ComponentCenter, InjuryReport, PowerCenter,
  RecordBook, TradeDesk, Transactions,
} from "./components";
import { TrendCenter } from "./TrendChart";
import { fmt, signed, teamName } from "./util";

const TABS = [
  ["board", "Big Board"],
  ["components", "Component Center"],
  ["power", "Power Rankings"],
  ["coaching", "Coaching Report"],
  ["wire", "Transaction Wire"],
  ["trades", "Trade Desk"],
  ["injury", "Injury Report"],
  ["records", "Record Book"],
  ["trend", "Trend Center"],
] as const;
type Tab = (typeof TABS)[number][0];

function tickerItems(d: LeagueData): { cat: string; text: string }[] {
  const items: { cat: string; text: string }[] = [];
  const luckiest = d.teams[0];
  const sob = d.teams[d.teams.length - 1];
  items.push({ cat: "BREAKING", text: `${luckiest.name.trim()} remains the league's luckiest team at ${signed(luckiest.luckIndex)} — sources say they feel "blessed"` });
  items.push({ cat: "SOB STORY", text: `${sob.name.trim()} checks in at ${signed(sob.luckIndex)} on the Luck Index — thoughts and prayers` });
  const lw = d.luckiestWins[0];
  if (lw) items.push({ cat: "LUCKBOX", text: `Wk ${lw.week}: ${teamName(d, lw.teamId!)} won with the week's #${lw.rank} score (${fmt(lw.points!, 1)}–${fmt(lw.oppPoints!, 1)})` });
  const tl = d.toughestLosses[0];
  if (tl) items.push({ cat: "ROBBED", text: `Wk ${tl.week}: ${teamName(d, tl.teamId!)} dropped ${fmt(tl.points!, 1)} and LOST` });
  const regretKing = [...d.teams].sort((a, b) => b.regretPoints - a.regretPoints)[0];
  const topDrop = regretKing.regretDetail[0];
  if (topDrop) items.push({ cat: "NOT TOP 10", text: `${regretKing.name.trim()} watched ${topDrop.player} score ${fmt(topDrop.pointsSince, 0)} pts since the drop — ${fmt(topDrop.ppgSince, 1)}/g` });
  const mash = [...d.teams].sort((a, b) => b.injuryPointsLost - a.injuryPointsLost)[0];
  items.push({ cat: "INJURY REPORT", text: `${mash.name.trim()} has lost ${fmt(mash.injuryPointsLost, 0)} starter points to injury — a league worst` });
  const rb = d.recordBook;
  items.push({ cat: "RECORD WATCH", text: `Season high: ${teamName(d, rb.highScores[0].teamId!)} ${fmt(rb.highScores[0].points!, 1)} (wk ${rb.highScores[0].week})` });
  items.push({ cat: "HEARTBREAK", text: `Narrowest win: ${fmt(rb.narrowestWin.margin!, 2)} pts, wk ${rb.narrowestWin.week} — ${teamName(d, rb.narrowestWin.winner!)} over ${teamName(d, rb.narrowestWin.loser!)}` });
  const eff = [...d.teams].sort((a, b) => a.efficiency - b.efficiency)[0];
  items.push({ cat: "COACHING", text: `${eff.name.trim()} has left ${fmt(eff.benchPointsLeft, 0)} points on the bench — the coaching staff declined comment` });
  return items;
}

export default function App() {
  const [data, setData] = useState<LeagueData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("board");

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/league.json`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  const ticker = useMemo(() => (data ? tickerItems(data) : []), [data]);

  if (err) return <div className="main"><div className="card">Failed to load league data: {err}</div></div>;
  if (!data) return <div className="main"><div className="card">Warming up the studio…</div></div>;

  return (
    <>
      <header className="masthead">
        <h1 className="logo">CTE<span>SPN</span></h1>
        <span className="tagline">The Worldwide Leader in Luck™ — {data.league}</span>
        <span className="live"><span className="live-dot" />LIVE · THROUGH WEEK {data.generatedWeekThrough}</span>
      </header>
      <div className="ticker-wrap">
        <div className="ticker-label">BOTTOMLINE</div>
        <div className="ticker">
          {[...ticker, ...ticker].map((it, i) => (
            <span className="ticker-item" key={i}>
              <span className="cat">{it.cat}</span>
              <b>{it.text}</b>
            </span>
          ))}
        </div>
      </div>
      <nav className="nav">
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </nav>
      <main className="main">
        {tab === "board" && <BigBoard data={data} />}
        {tab === "components" && <ComponentCenter data={data} />}
        {tab === "power" && <PowerCenter data={data} />}
        {tab === "coaching" && <CoachingReport data={data} />}
        {tab === "wire" && <Transactions data={data} />}
        {tab === "trades" && <TradeDesk data={data} />}
        {tab === "injury" && <InjuryReport data={data} />}
        {tab === "records" && <RecordBook data={data} />}
        {tab === "trend" && <TrendCenter data={data} />}
      </main>
      <footer>
        CTESPN is a parody and is not affiliated with ESPN. All sob stories are real.
        Data: ESPN Fantasy · Season {data.season}
      </footer>
    </>
  );
}
