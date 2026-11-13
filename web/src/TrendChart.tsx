import { useMemo, useRef, useState } from "react";
import type { LeagueData } from "./types";
import { fmt, signed, teamName } from "./util";

const W = 920, H = 380, PAD = { t: 18, r: 120, b: 34, l: 48 };

export function TrendCenter({ data }: { data: LeagueData }) {
  const teams = data.teams;
  const [sel, setSel] = useState<number>(teams[0]?.teamId ?? 1);
  const [hover, setHover] = useState<{ x: number; y: number; week: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const { weeks, series, yMin, yMax } = useMemo(() => {
    const weeks = [...new Set(data.luckTrend.map((r) => r.week))].sort((a, b) => a - b);
    const series = new Map<number, { week: number; luck: number }[]>();
    for (const r of data.luckTrend) {
      if (!series.has(r.teamId)) series.set(r.teamId, []);
      series.get(r.teamId)!.push({ week: r.week, luck: r.luck });
    }
    const all = data.luckTrend.map((r) => r.luck);
    return {
      weeks, series,
      yMin: Math.min(...all, -50) - 10,
      yMax: Math.max(...all, 50) + 10,
    };
  }, [data]);

  const x = (wk: number) =>
    PAD.l + ((wk - weeks[0]) / (weeks[weeks.length - 1] - weeks[0])) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - yMin) / (yMax - yMin)) * (H - PAD.t - PAD.b);

  const path = (pts: { week: number; luck: number }[]) =>
    pts.map((p, i) => `${i ? "L" : "M"}${fmt(x(p.week), 1)},${fmt(y(p.luck), 1)}`).join("");

  const hoverWeek = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    let best = weeks[0];
    for (const wk of weeks) if (Math.abs(x(wk) - px) < Math.abs(x(best) - px)) best = wk;
    setHover({ x: e.clientX - rect.left, y: e.clientY - rect.top, week: best });
  };

  const selPts = series.get(sel) ?? [];
  const hoverVal = hover ? selPts.find((p) => p.week === hover.week)?.luck : undefined;

  return (
    <>
      <h2 className="segment-title">Trend Center</h2>
      <p className="segment-sub">
        Luck Index by week — pick a team to light them up. Everyone converges on the
        truth eventually; the question is whether the playoffs arrive first.
      </p>
      <div className="card">
        <div className="trend-controls" role="tablist" aria-label="Highlight team">
          {teams.map((t) => (
            <button
              key={t.teamId}
              className={"chip" + (sel === t.teamId ? " on" : "")}
              onClick={() => setSel(t.teamId)}
            >
              {t.name.trim()}
            </button>
          ))}
        </div>
        <div ref={wrapRef} style={{ position: "relative" }}>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            style={{ width: "100%", display: "block" }}
            onMouseMove={hoverWeek}
            onMouseLeave={() => setHover(null)}
            role="img"
            aria-label="Luck Index trend by week"
          >
            {/* gridlines + axis */}
            {[yMin + 10, 0, yMax - 10].map((v) => (
              <g key={v}>
                <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)}
                  stroke={v === 0 ? "var(--neutral-mid)" : "var(--line)"}
                  strokeWidth={1} strokeDasharray={v === 0 ? "" : "3 4"} />
                <text x={PAD.l - 8} y={y(v) + 4} textAnchor="end" fontSize={11.5}
                  fill="var(--ink-3)">{fmt(v, 0)}</text>
              </g>
            ))}
            {weeks.map((wk) => (
              <text key={wk} x={x(wk)} y={H - 10} textAnchor="middle" fontSize={11.5}
                fill="var(--ink-3)">wk {wk}</text>
            ))}
            {/* background lines */}
            {teams.filter((t) => t.teamId !== sel).map((t) => (
              <path key={t.teamId} d={path(series.get(t.teamId) ?? [])} fill="none"
                stroke="var(--line)" strokeWidth={1.5} />
            ))}
            {/* selected line on top with surface ring */}
            <path d={path(selPts)} fill="none" stroke="var(--surface)" strokeWidth={5} />
            <path d={path(selPts)} fill="none" stroke="var(--accent-bright)" strokeWidth={2.5} />
            {selPts.map((p) => (
              <circle key={p.week} cx={x(p.week)} cy={y(p.luck)} r={4}
                fill="var(--accent-bright)" stroke="var(--surface)" strokeWidth={2} />
            ))}
            {selPts.length > 0 && (
              <text x={x(selPts[selPts.length - 1].week) + 8}
                y={y(selPts[selPts.length - 1].luck) + 4}
                fontSize={12.5} fontWeight={600} fill="var(--ink)">
                {teamName(data, sel)}
              </text>
            )}
            {hover && (
              <line x1={x(hover.week)} x2={x(hover.week)} y1={PAD.t} y2={H - PAD.b}
                stroke="var(--neutral-mid)" strokeWidth={1} strokeDasharray="2 3" />
            )}
          </svg>
          {hover && hoverVal !== undefined && (
            <div className="tooltip" style={{
              left: Math.min(hover.x + 14, (wrapRef.current?.clientWidth ?? W) - 150),
              top: hover.y - 10,
            }}>
              <div className="tt-week">Through week {hover.week}</div>
              <div><b>{teamName(data, sel)}</b> {signed(hoverVal)}</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
