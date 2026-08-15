import { useState, useEffect } from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Legend,
} from "recharts";
import ReactMarkdown from "react-markdown";

const API = import.meta.env.VITE_API_BASE_URL || "/api";

const LANES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"];

function confidenceColor(c) {
  return { high: "#22c55e", medium: "#eab308", low: "#ef4444" }[c] || "#888";
}

function ItemRows({ list, edgeLabel, version }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr style={{ textAlign: "left", color: "#888", fontSize: 13 }}>
          <th>Item</th><th>Games</th><th>Win rate</th><th>{edgeLabel}</th>
        </tr>
      </thead>
      <tbody>
        {list.slice(0, 8).map((it) => (
          <tr key={it.item} style={{ borderTop: "1px solid #eee" }}>
            <td style={{ padding: "6px 0", display: "flex", alignItems: "center", gap: 8 }}>
              {version && it.item_id && (
                <img
                  src={`https://ddragon.leagueoflegends.com/cdn/${version}/img/item/${it.item_id}.png`}
                  alt="" width={24} height={24}
                  style={{ borderRadius: 4, verticalAlign: "middle" }}
                />
              )}
              {it.item}
            </td>
            <td>{it.games}</td>
            <td>{(it.shrunk_winrate * 100).toFixed(1)}%</td>
            <td style={{ color: it.edge >= 0 ? "#22c55e" : "#ef4444" }}>
              {it.edge >= 0 ? "+" : ""}{(it.edge * 100).toFixed(1)}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
function ShrinkageChart({ data, prior }) {
  // sparse items first, so the "pulled hard" rows read at the top
  const rows = [...data]
    .sort((a, b) => a.games - b.games)
    .slice(0, 10)
    .map((it) => ({
      item: it.item,
      games: it.games,
      raw: +(it.raw_winrate * 100).toFixed(1),
      shrunk: +(it.shrunk_winrate * 100).toFixed(1),
    }));
 
  if (rows.length === 0) return null;
 
  return (
    <div style={cardStyle}>
      <h3 style={{ marginTop: 0, color: "#1a1a1a" }}>Shrinkage: raw vs. corrected</h3>
      <p style={{ color: "#888", fontSize: 13, marginTop: -4 }}>
        Grey = raw win rate, purple = shrunk estimate. The wider the gap, the smaller the sample:
        sparse items get pulled toward the baseline, well-sampled ones barely move.
      </p>
      <ResponsiveContainer width="100%" height={Math.max(240, rows.length * 36)}>
        <ScatterChart margin={{ left: 30, right: 24, top: 10, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" dataKey="value" domain={[0, 100]} unit="%" tick={{ fontSize: 12 }} />
          <YAxis type="category" dataKey="item" width={130} tick={{ fontSize: 12 }} allowDuplicatedCategory={false} />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            formatter={(v, name, props) => [`${v}%`, name]}
            labelFormatter={() => ""}
          />
          <ReferenceLine x={+(prior * 100).toFixed(1)} stroke="#f59e0b" strokeDasharray="4 4"
            label={{ value: "baseline", position: "top", fontSize: 11, fill: "#f59e0b" }} />
          <Scatter name="Raw"    data={rows.map((r) => ({ item: r.item, value: r.raw }))}    fill="#9ca3af" />
          <Scatter name="Shrunk" data={rows.map((r) => ({ item: r.item, value: r.shrunk }))} fill="#7c3aed" />
          <Legend />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function App() {
  const [champion, setChampion] = useState("Yasuo");
  const [opponent, setOpponent] = useState("Ahri");
  const [championList, setChampionList] = useState([]);
  const [lane, setLane] = useState("MIDDLE");
  const [matchup, setMatchup] = useState(null);
  const [personal, setPersonal] = useState(null);
  const [items, setItems] = useState(null);
  const [matchupItems, setMatchupItems] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [explanation, setExplanation] = useState(null);
  const [explaining, setExplaining] = useState(false);

  useEffect(() => {
    fetch('${API}/champions')
      .then((r) => r.json())
      .then((d) => setChampionList(d.champions))
      .catch(() => {});
  }, []);

  async function analyze() {
    setLoading(true);
    setError(null);
    setMatchup(null);
    setPersonal(null);
    setItems(null);
    setMatchupItems(null);
    setExplanation(null);
    try {
      const mRes = await fetch(
        `${API}/matchup?champion=${champion}&opponent=${opponent}&lane=${lane}`
      );
      if (!mRes.ok) throw new Error("No data for that matchup");
      setMatchup(await mRes.json());

      const pRes = await fetch(
        `${API}/personal?champion=${champion}&opponent=${opponent}&lane=${lane}`
      );
      setPersonal(pRes.ok ? await pRes.json() : null);

      const iRes = await fetch(`${API}/items?champion=${champion}`);
      setItems(iRes.ok ? await iRes.json() : null);

      const miRes = await fetch(
        `${API}/matchup-items?champion=${champion}&opponent=${opponent}&lane=${lane}`
      );
      setMatchupItems(miRes.ok ? await miRes.json() : null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function explain() {
    setExplaining(true);
    try {
      const res = await fetch(`${API}/explain?champion=${champion}&opponent=${opponent}&lane=${lane}`);
      if (res.ok) setExplanation((await res.json()).explanation);
    } finally {
      setExplaining(false);
    }
  }

  return (
    <div style={{ maxWidth: 680, margin: "40px auto", fontFamily: "system-ui, sans-serif", padding: 20 }}>
      <h1 style={{ fontSize: 28 }}>LoL Matchup Analytics</h1>
      <p style={{ color: "#666", marginTop: -8 }}>
        Bayesian-shrunk win rates — every number shows how much data backs it.
      </p>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 20 }}>
        <select value={champion} onChange={(e) => setChampion(e.target.value)} style={inputStyle}>
          {championList.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={opponent} onChange={(e) => setOpponent(e.target.value)} style={inputStyle}>
          {championList.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={lane} onChange={(e) => setLane(e.target.value)} style={inputStyle}>
          {LANES.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <button onClick={analyze} disabled={loading} style={buttonStyle}>
          {loading ? "..." : "Analyze"}
        </button>
      </div>

      {error && <p style={{ color: "#ef4444", marginTop: 20 }}>{error}</p>}

      {matchup && (
        <div style={cardStyle}>
          <h2 style={{ margin: 0, color: "#1a1a1a", fontSize: 20 }}>
            {matchup.champion} vs {matchup.opponent} · {matchup.lane}
          </h2>
          <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginTop: 12 }}>
            <span style={{ fontSize: 40, fontWeight: 700 }}>
              {(matchup.shrunk_winrate * 100).toFixed(1)}%
            </span>
            <span style={{
              padding: "3px 10px", borderRadius: 12, fontSize: 13, fontWeight: 600,
              color: "#fff", background: confidenceColor(matchup.confidence),
            }}>
              {matchup.confidence} confidence
            </span>
          </div>
          <p style={{ color: "#666", marginTop: 8 }}>
            Based on <strong>{matchup.games} games</strong>.
            Raw rate {(matchup.raw_winrate * 100).toFixed(1)}% — shrunk toward the population baseline
            because {matchup.games < 30 ? "the sample is small" : "of the population prior"}.
          </p>
        </div>
      )}

      {matchup && !explanation && (
        <button onClick={explain} disabled={explaining} style={{ ...buttonStyle, marginTop: 12, background: "#7c3aed" }}>
          {explaining ? "Thinking..." : "Get AI coaching summary"}
        </button>
      )}

      {explanation && (
        <div style={{
          marginTop: 20, padding: "20px 24px", borderRadius: 12,
          background: "linear-gradient(135deg, #faf5ff 0%, #f5f3ff 100%)",
          border: "1px solid #e9d5ff",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 18 }}></span>
            <span style={{ fontSize: 13, color: "#7c3aed", fontWeight: 700, letterSpacing: 0.5 }}>
              AI COACHING SUMMARY
            </span>
          </div>
          <div style={{ color: "#3b0764", lineHeight: 1.65, fontSize: 15 }}>
            <ReactMarkdown
              components={{
                strong: ({ children }) => <strong style={{ color: "#7c3aed" }}>{children}</strong>,
                p: ({ children }) => <p style={{ margin: "0 0 8px" }}>{children}</p>,
              }}
            >
              {explanation}
            </ReactMarkdown>
          </div>
        </div>
      )}

      {personal && (
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0, color: "#1a1a1a" }}>
            Your history · {personal.games} games
          </h3>
          <div style={{ display: "flex", gap: 24, alignItems: "baseline" }}>
            <div>
              <div style={{ fontSize: 32, fontWeight: 700 }}>
                {(personal.shrunk_winrate * 100).toFixed(1)}%
              </div>
              <div style={{ color: "#888", fontSize: 13 }}>your shrunk rate</div>
            </div>
            <div>
              <div style={{ fontSize: 32, fontWeight: 700, color: "#999" }}>
                {(personal.population_winrate * 100).toFixed(1)}%
              </div>
              <div style={{ color: "#888", fontSize: 13 }}>population</div>
            </div>
            <div>
              <div style={{
                fontSize: 32, fontWeight: 700,
                color: personal.edge >= 0 ? "#22c55e" : "#ef4444",
              }}>
                {personal.edge >= 0 ? "+" : ""}{(personal.edge * 100).toFixed(1)}%
              </div>
              <div style={{ color: "#888", fontSize: 13 }}>{personal.verdict}</div>
            </div>
          </div>
        </div>
      )}
      {matchupItems && matchupItems.items.length > 0 && (
        <ShrinkageChart data={matchupItems.items} prior={matchup ? matchup.shrunk_winrate : 0.5} />
      )}

      {matchupItems && matchupItems.items.length > 0 && (
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0, color: "#1a1a1a" }}>
            Items vs {matchupItems.opponent}
          </h3>
          <p style={{ color: "#888", fontSize: 13, marginTop: -4 }}>
            Edge is vs {matchupItems.champion}'s general build — positive means the item does even
            better into {matchupItems.opponent} specifically (shrunk hard, since matchup samples are small).
          </p>
          <ItemRows list={matchupItems.items} edgeLabel="Edge vs general" version={matchupItems.version} />
        </div>
      )}

      {items && items.items.length > 0 && (
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0, color: "#1a1a1a" }}>Top items for {items.champion}</h3>
          <p style={{ color: "#888", fontSize: 13, marginTop: -4 }}>
            Champion-wide (all matchups), ranked by shrunk edge over {items.champion}'s baseline.
          </p>
          <ItemRows list={items.items} edgeLabel="Edge" version={items.version} />
        </div>
      )}
    </div>
  );
}

const inputStyle = { padding: "8px 10px", fontSize: 15, border: "1px solid #ccc", borderRadius: 6 };
const buttonStyle = { padding: "8px 18px", fontSize: 15, fontWeight: 600, background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" };
const cardStyle = { marginTop: 20, padding: 20, border: "1px solid #eee", borderRadius: 10, background: "#fafafa" };