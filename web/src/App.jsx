import { useState, useEffect } from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Legend,
} from "recharts";
import ReactMarkdown from "react-markdown";

// The JSON files made by pipeline/build.py sit next to the page in data/.
// BASE_URL keeps this working both locally and on GitHub Pages.
const DATA = `${import.meta.env.BASE_URL}data`;

const LANES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"];
const KEY_STORAGE = "anthropic_api_key";

// champion files already downloaded this visit, so switching back is instant
const championCache = {};

async function loadChampion(id) {
  if (!championCache[id]) {
    const res = await fetch(`${DATA}/champions/${id}.json`);
    if (!res.ok) throw new Error(`Could not load data for ${id}`);
    championCache[id] = await res.json();
  }
  return championCache[id];
}

// table[lane][opponent], or null when we have no games for it
function lookup(table, lane, opponent) {
  if (!table[lane]) return null;
  return table[lane][opponent] || null;
}

// localStorage can be blocked (private windows); never let that crash the page
function readSavedKey() {
  try {
    return localStorage.getItem(KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

function writeSavedKey(value) {
  try {
    if (value) localStorage.setItem(KEY_STORAGE, value);
    else localStorage.removeItem(KEY_STORAGE);
  } catch {
    // nothing to do; the key just won't be remembered
  }
}

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
          <tr key={it.item_id} style={{ borderTop: "1px solid #eee" }}>
            <td style={{ padding: "6px 0", display: "flex", alignItems: "center", gap: 8 }}>
              {version && (
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
            formatter={(v, name) => [`${v}%`, name]}
            labelFormatter={() => ""}
          />
          <ReferenceLine x={+(prior * 100).toFixed(1)} stroke="#f59e0b" strokeDasharray="4 4"
            label={{ value: "baseline", position: "top", fontSize: 11, fill: "#f59e0b" }} />
          <Scatter name="Raw" data={rows.map((r) => ({ item: r.item, value: r.raw }))} fill="#9ca3af" />
          <Scatter name="Shrunk" data={rows.map((r) => ({ item: r.item, value: r.shrunk }))} fill="#7c3aed" />
          <Legend />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function App() {
  const [index, setIndex] = useState(null);           // index.json: champion list + build info
  const [champion, setChampion] = useState("Yasuo");  // Data Dragon ids, e.g. "MonkeyKing"
  const [opponent, setOpponent] = useState("Ahri");
  const [lane, setLane] = useState("MIDDLE");
  const [result, setResult] = useState(null);         // everything shown after Analyze
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [apiKey, setApiKey] = useState(readSavedKey());
  const [keyDraft, setKeyDraft] = useState("");
  const [explanation, setExplanation] = useState(null);
  const [explainError, setExplainError] = useState(null);
  const [explaining, setExplaining] = useState(false);

  useEffect(() => {
    fetch(`${DATA}/index.json`)
      .then((r) => r.json())
      .then((d) => setIndex(d))
      .catch(() => setError("Could not load the champion list. Has pipeline/build.py been run?"));
  }, []);

  // id -> display name, e.g. "MonkeyKing" -> "Wukong"
  const names = {};
  if (index) {
    for (const c of index.champions) names[c.id] = c.name;
  }

  async function analyze() {
    setLoading(true);
    setError(null);
    setResult(null);
    setExplanation(null);
    setExplainError(null);
    try {
      const data = await loadChampion(champion);
      const matchup = lookup(data.matchups, lane, opponent);
      if (!matchup) {
        throw new Error(`No games yet for ${names[champion]} vs ${names[opponent]} in ${lane}.`);
      }
      setResult({
        championName: names[champion],
        opponentName: names[opponent],
        lane: lane,
        matchup: matchup,
        personal: lookup(data.personal, lane, opponent),
        items: data.items,
        matchupItems: lookup(data.matchup_items, lane, opponent) || [],
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function saveKey() {
    const trimmed = keyDraft.trim();
    writeSavedKey(trimmed);
    setApiKey(trimmed);
    setKeyDraft("");
  }

  function forgetKey() {
    writeSavedKey("");
    setApiKey("");
  }

  async function explain() {
    setExplaining(true);
    setExplainError(null);
    let coach = null;
    try {
      // load the AI code (and the Anthropic SDK) only on first click,
      // so people who never use it don't download it
      coach = await import("./coach.js");
      const facts = coach.buildFacts(
        result.championName, result.opponentName, result.lane,
        result.matchup, result.personal, result.items, result.matchupItems,
      );
      setExplanation(await coach.getCoachingSummary(apiKey, facts));
    } catch (e) {
      setExplainError(coach ? coach.describeError(e) : e.message);
    } finally {
      setExplaining(false);
    }
  }

  const champions = index ? index.champions : [];
  const version = index ? index.ddragon_version : null;

  return (
    <div style={{ maxWidth: 680, margin: "40px auto", fontFamily: "system-ui, sans-serif", padding: 20 }}>
      <h1 style={{ fontSize: 28 }}>LoL Matchup Analytics</h1>
      <p style={{ color: "#666", marginTop: -8 }}>
        Bayesian-shrunk win rates. Every number shows how much data backs it.
      </p>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 20 }}>
        <select value={champion} onChange={(e) => setChampion(e.target.value)} style={inputStyle}>
          {champions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={opponent} onChange={(e) => setOpponent(e.target.value)} style={inputStyle}>
          {champions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={lane} onChange={(e) => setLane(e.target.value)} style={inputStyle}>
          {LANES.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <button onClick={analyze} disabled={loading || !index} style={buttonStyle}>
          {loading ? "..." : "Analyze"}
        </button>
      </div>

      {error && <p style={{ color: "#ef4444", marginTop: 20 }}>{error}</p>}

      {result && (
        <div style={cardStyle}>
          <h2 style={{ margin: 0, color: "#1a1a1a", fontSize: 20 }}>
            {result.championName} vs {result.opponentName} · {result.lane}
          </h2>
          <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginTop: 12 }}>
            <span style={{ fontSize: 40, fontWeight: 700 }}>
              {(result.matchup.shrunk_winrate * 100).toFixed(1)}%
            </span>
            <span style={{
              padding: "3px 10px", borderRadius: 12, fontSize: 13, fontWeight: 600,
              color: "#fff", background: confidenceColor(result.matchup.confidence),
            }}>
              {result.matchup.confidence} confidence
            </span>
          </div>
          <p style={{ color: "#666", marginTop: 8 }}>
            Based on <strong>{result.matchup.games} games</strong>.
            Raw rate {(result.matchup.raw_winrate * 100).toFixed(1)}%, shrunk toward{" "}
            {result.championName}'s {(result.matchup.prior * 100).toFixed(1)}% lane baseline
            {result.matchup.games < 30 ? " because the sample is small." : "."}
          </p>
        </div>
      )}

      {result && !explanation && (
        <div style={{ marginTop: 12 }}>
          {apiKey ? (
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <button onClick={explain} disabled={explaining} style={{ ...buttonStyle, background: "#7c3aed" }}>
                {explaining ? "Thinking..." : "Get AI coaching summary"}
              </button>
              <button onClick={forgetKey} style={linkStyle}>forget my API key</button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <input
                type="password"
                placeholder="Anthropic API key for AI summaries"
                value={keyDraft}
                onChange={(e) => setKeyDraft(e.target.value)}
                style={{ ...inputStyle, flex: 1, minWidth: 220 }}
              />
              <button onClick={saveKey} disabled={!keyDraft.trim()} style={{ ...buttonStyle, background: "#7c3aed" }}>
                Save key
              </button>
              <p style={{ color: "#888", fontSize: 12, margin: 0, width: "100%" }}>
                Optional. The key stays in this browser and is sent only to Anthropic.
              </p>
            </div>
          )}
          {explainError && <p style={{ color: "#ef4444" }}>{explainError}</p>}
        </div>
      )}

      {explanation && (
        <div style={{
          marginTop: 20, padding: "20px 24px", borderRadius: 12,
          background: "linear-gradient(135deg, #faf5ff 0%, #f5f3ff 100%)",
          border: "1px solid #e9d5ff",
        }}>
          <div style={{ fontSize: 13, color: "#7c3aed", fontWeight: 700, letterSpacing: 0.5, marginBottom: 10 }}>
            AI COACHING SUMMARY
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

      {result && result.personal && (
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0, color: "#1a1a1a" }}>
            Your history · {result.personal.games} games
          </h3>
          <div style={{ display: "flex", gap: 24, alignItems: "baseline" }}>
            <div>
              <div style={{ fontSize: 32, fontWeight: 700 }}>
                {(result.personal.shrunk_winrate * 100).toFixed(1)}%
              </div>
              <div style={{ color: "#888", fontSize: 13 }}>your shrunk rate</div>
            </div>
            <div>
              <div style={{ fontSize: 32, fontWeight: 700, color: "#999" }}>
                {(result.personal.population_winrate * 100).toFixed(1)}%
              </div>
              <div style={{ color: "#888", fontSize: 13 }}>population</div>
            </div>
            <div>
              <div style={{
                fontSize: 32, fontWeight: 700,
                color: result.personal.edge >= 0 ? "#22c55e" : "#ef4444",
              }}>
                {result.personal.edge >= 0 ? "+" : ""}{(result.personal.edge * 100).toFixed(1)}%
              </div>
              <div style={{ color: "#888", fontSize: 13 }}>{result.personal.verdict}</div>
            </div>
          </div>
        </div>
      )}

      {result && result.matchupItems.length > 0 && (
        <ShrinkageChart data={result.matchupItems} prior={result.matchup.shrunk_winrate} />
      )}

      {result && result.matchupItems.length > 0 && (
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0, color: "#1a1a1a" }}>Items vs {result.opponentName}</h3>
          <p style={{ color: "#888", fontSize: 13, marginTop: -4 }}>
            Edge is vs {result.championName}'s general build. Positive means the item does even
            better into {result.opponentName} specifically (shrunk hard, since matchup samples are small).
          </p>
          <ItemRows list={result.matchupItems} edgeLabel="Edge vs general" version={version} />
        </div>
      )}

      {result && result.items.length > 0 && (
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0, color: "#1a1a1a" }}>Top items for {result.championName}</h3>
          <p style={{ color: "#888", fontSize: 13, marginTop: -4 }}>
            Champion-wide (all matchups), ranked by shrunk edge over {result.championName}'s baseline.
          </p>
          <ItemRows list={result.items} edgeLabel="Edge" version={version} />
        </div>
      )}

      {index && (
        <p style={{ color: "#aaa", fontSize: 12, marginTop: 32 }}>
          {index.match_count} ranked matches from {index.first_game} to {index.last_game} ·
          patch {index.ddragon_version} · shrinkage strength K = {index.k} · updated {index.built_at}
        </p>
      )}
    </div>
  );
}

const inputStyle = { padding: "8px 10px", fontSize: 15, border: "1px solid #ccc", borderRadius: 6 };
const buttonStyle = { padding: "8px 18px", fontSize: 15, fontWeight: 600, background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" };
const linkStyle = { background: "none", border: "none", color: "#888", fontSize: 13, textDecoration: "underline", cursor: "pointer", padding: 0 };
// cards are always light, so their text is always dark (even when the browser is in dark mode)
const cardStyle = { marginTop: 20, padding: 20, border: "1px solid #eee", borderRadius: 10, background: "#fafafa", color: "#1a1a1a" };
