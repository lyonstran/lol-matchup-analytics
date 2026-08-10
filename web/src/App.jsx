import { useState, useEffect } from "react";

const LANES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"];

function confidenceColor(c) {
  return { high: "#22c55e", medium: "#eab308", low: "#ef4444" }[c] || "#888";
}

export default function App() {
  const [champion, setChampion] = useState("Yasuo");
  const [opponent, setOpponent] = useState("Ahri");
  const [championList, setChampionList] = useState([]);
  const [lane, setLane] = useState("MIDDLE");
  const [matchup, setMatchup] = useState(null);
  const [personal, setPersonal] = useState(null);
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/champions")
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
    try {
      const mRes = await fetch(
        `/api/matchup?champion=${champion}&opponent=${opponent}&lane=${lane}`
      );
      if (!mRes.ok) throw new Error("No data for that matchup");
      setMatchup(await mRes.json());

      const pRes = await fetch(
        `/api/personal?champion=${champion}&opponent=${opponent}&lane=${lane}`
      );
      setPersonal(pRes.ok ? await pRes.json() : null);

      const iRes = await fetch(`/api/items?champion=${champion}`);
      if (iRes.ok) setItems(await iRes.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
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

      {items && items.items.length > 0 && (
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0, color: "#1a1a1a" }}>Top items for {items.champion} (by edge)</h3>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", color: "#888", fontSize: 13 }}>
                <th>Item</th><th>Games</th><th>Win rate</th><th>Edge</th>
              </tr>
            </thead>
            <tbody>
              {items.items.slice(0, 8).map((it) => (
                <tr key={it.item} style={{ borderTop: "1px solid #eee" }}>
                  <td style={{ padding: "6px 0" }}>{it.item}</td>
                  <td>{it.games}</td>
                  <td>{(it.shrunk_winrate * 100).toFixed(1)}%</td>
                  <td style={{ color: it.edge >= 0 ? "#22c55e" : "#ef4444" }}>
                    {it.edge >= 0 ? "+" : ""}{(it.edge * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const inputStyle = { padding: "8px 10px", fontSize: 15, border: "1px solid #ccc", borderRadius: 6 };
const buttonStyle = { padding: "8px 18px", fontSize: 15, fontWeight: 600, background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" };
const cardStyle = { marginTop: 20, padding: 20, border: "1px solid #eee", borderRadius: 10, background: "#fafafa" };