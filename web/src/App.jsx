import { useState, useEffect } from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Legend,
} from "recharts";
import ReactMarkdown from "react-markdown";

// The JSON files made by pipeline/build.py sit next to the page in data/.
// BASE_URL keeps this working both locally and on GitHub Pages.
const DATA = `${import.meta.env.BASE_URL}data`;

// Riot's lane names, and the names players actually use
const LANES = [
  { id: "TOP", label: "Top" },
  { id: "JUNGLE", label: "Jungle" },
  { id: "MIDDLE", label: "Mid" },
  { id: "BOTTOM", label: "Bot" },
  { id: "UTILITY", label: "Support" },
];
const KEY_STORAGE = "anthropic_api_key";

// chart colors (the same values as --shrunk, --raw, --grid, --axis, --ink-muted in index.css)
const SHRUNK_COLOR = "#3987e5";
const RAW_COLOR = "#d95926";
const GRID_COLOR = "#2c2c2a";
const AXIS_COLOR = "#383835";
const MUTED_COLOR = "#898781";
const CONNECTOR_COLOR = "#5f5e5a";   // the raw-to-shrunk line: visible, but quieter than the dots

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

// 0.523 -> "52.3%"
function pct(x) {
  return (x * 100).toFixed(1) + "%";
}

// 0.031 -> "+3.1%", -0.031 -> "-3.1%"
function signedPct(x) {
  const sign = x >= 0 ? "+" : "";
  return sign + (x * 100).toFixed(1) + "%";
}

function laneLabel(id) {
  for (const l of LANES) {
    if (l.id === id) return l.label;
  }
  return id;
}

// ---------- small building blocks ----------

function ConfidenceBadge({ level }) {
  return <span className={`badge ${level}`}>{level} confidence</span>;
}

// one headline tile in the top row
function Tile({ label, value, small, sub, children }) {
  return (
    <div className="panel">
      <div className="tile-label">{label}</div>
      <div className={small ? "tile-value small" : "tile-value"}>
        {value}
        {children}
      </div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}

// a bar from the center line: right and blue for a positive edge, left and red for negative.
// A full half-bar means an edge of 10 points or more.
function EdgeBar({ edge }) {
  const halfWidth = Math.min(Math.abs(edge) / 0.10, 1) * 50;   // percent of the track
  const style = { width: `${halfWidth}%` };
  if (edge >= 0) {
    style.left = "50%";
    style.background = "var(--edge-up)";
  } else {
    style.right = "50%";
    style.background = "var(--edge-down)";
  }
  return (
    <div className="edge-cell">
      <div className="edge-track">
        <div className="zero" />
        <div className="bar" style={style} />
      </div>
      <span className="edge-number">{signedPct(edge)}</span>
    </div>
  );
}

function ItemTable({ list, edgeLabel, version }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th className="num">Games</th>
            <th className="num">Win rate</th>
            <th className="num">{edgeLabel}</th>
          </tr>
        </thead>
        <tbody>
          {list.map((it) => (
            <tr key={it.item_id}>
              <td>
                <div className="item-cell">
                  {version && (
                    <img
                      src={`https://ddragon.leagueoflegends.com/cdn/${version}/img/item/${it.item_id}.png`}
                      alt="" width={22} height={22}
                    />
                  )}
                  {it.item}
                </div>
              </td>
              <td className="num">{it.games}</td>
              <td className="num">{pct(it.shrunk_winrate)}</td>
              <td className="num"><EdgeBar edge={it.edge} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// hover box for the chart: the item, its sample size, raw and shrunk
function ChartTooltip({ active, payload }) {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0].payload;
  return (
    <div className="panel" style={{ padding: "8px 10px", fontSize: 12 }}>
      <strong>{row.item}</strong> · {row.games} games
      <div style={{ color: RAW_COLOR }}>raw {row.raw}%</div>
      <div style={{ color: SHRUNK_COLOR }}>shrunk {row.shrunk}%</div>
    </div>
  );
}

// Raw vs shrunk for the items into this opponent: a line from the raw dot to the
// shrunk dot shows how far the estimate was pulled. Sparse items at the top.
function ShrinkageChart({ items }) {
  const rows = [];
  const sorted = [...items].sort((a, b) => a.games - b.games).slice(0, 6);
  for (const it of sorted) {
    rows.push({
      label: `${it.item} (${it.games})`,
      item: it.item,
      games: it.games,
      raw: +(it.raw_winrate * 100).toFixed(1),
      shrunk: +(it.shrunk_winrate * 100).toFixed(1),
    });
  }

  // zoom the x axis to the data (with a little room) instead of always 0-100%
  let low = 50;
  let high = 50;
  for (const r of rows) {
    low = Math.min(low, r.raw, r.shrunk);
    high = Math.max(high, r.raw, r.shrunk);
  }
  low = Math.max(0, Math.floor((low - 5) / 10) * 10);
  high = Math.min(100, Math.ceil((high + 5) / 10) * 10);

  const rawPoints = [];
  const shrunkPoints = [];
  for (const r of rows) {
    rawPoints.push({ ...r, x: r.raw });
    shrunkPoints.push({ ...r, x: r.shrunk });
  }

  return (
    <ResponsiveContainer width="100%" height={Math.max(170, rows.length * 30 + 50)}>
      <ScatterChart margin={{ left: 0, right: 16, top: 8, bottom: 0 }}>
        <CartesianGrid stroke={GRID_COLOR} horizontal={false} />
        <XAxis
          type="number" dataKey="x" domain={[low, high]} unit="%"
          tick={{ fontSize: 11, fill: MUTED_COLOR }} stroke={AXIS_COLOR}
        />
        <YAxis
          type="category" dataKey="label" width={170} allowDuplicatedCategory={false}
          tick={{ fontSize: 11, fill: MUTED_COLOR }} stroke={AXIS_COLOR}
        />
        <ReferenceLine x={50} stroke={MUTED_COLOR} strokeDasharray="4 4" />
        {rows.map((r) => (
          <ReferenceLine
            key={r.label}
            segment={[{ x: r.raw, y: r.label }, { x: r.shrunk, y: r.label }]}
            stroke={CONNECTOR_COLOR} strokeWidth={2}
          />
        ))}
        <Tooltip content={<ChartTooltip />} cursor={false} />
        {/* no grow-in animation: the dots should be there the moment the panel shows */}
        <Scatter name="Raw" data={rawPoints} fill={RAW_COLOR} isAnimationActive={false} />
        <Scatter name="Shrunk" data={shrunkPoints} fill={SHRUNK_COLOR} isAnimationActive={false} />
        <Legend iconSize={10} wrapperStyle={{ fontSize: 12, color: MUTED_COLOR }} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

// ---------- the AI coaching panel ----------

function CoachPanel({ result }) {
  const [apiKey, setApiKey] = useState(readSavedKey());
  const [keyDraft, setKeyDraft] = useState("");
  const [explanation, setExplanation] = useState(null);
  const [explainError, setExplainError] = useState(null);
  const [explaining, setExplaining] = useState(false);

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

  return (
    <div className="panel ai-panel">
      <h2>AI coaching summary</h2>
      <p className="caption">
        Written by Claude from the numbers on this page only, with small samples flagged.
      </p>

      {explanation && (
        <div className="ai-text">
          <ReactMarkdown>{explanation}</ReactMarkdown>
        </div>
      )}

      {!explanation && !apiKey && (
        <div>
          <div className="key-row">
            <input
              type="password"
              placeholder="Anthropic API key"
              value={keyDraft}
              onChange={(e) => setKeyDraft(e.target.value)}
            />
            <button className="button ai" onClick={saveKey} disabled={!keyDraft.trim()}>
              Save key
            </button>
          </div>
          <p className="caption">Optional. The key stays in this browser and is sent only to Anthropic.</p>
        </div>
      )}

      {!explanation && apiKey && (
        <div className="key-row">
          <button className="button ai" onClick={explain} disabled={explaining || !result.matchup}>
            {explaining ? "Thinking..." : "Write a summary"}
          </button>
          <button className="link-button" onClick={forgetKey}>forget my API key</button>
        </div>
      )}

      {explainError && <p className="error">{explainError}</p>}
    </div>
  );
}

// ---------- the page ----------

export default function App() {
  const [index, setIndex] = useState(null);           // index.json: champion list + build info
  const [champion, setChampion] = useState("Yasuo");  // Data Dragon ids, e.g. "MonkeyKing"
  const [opponent, setOpponent] = useState("Ahri");
  const [lane, setLane] = useState("MIDDLE");
  const [result, setResult] = useState(null);         // everything the panels show
  const [error, setError] = useState(null);

  // load the champion list once
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

  // Re-load the panels whenever a picker changes (no Analyze button needed).
  // `cancelled` stops a slow, older request from overwriting a newer one.
  useEffect(() => {
    if (!index) return;
    let cancelled = false;

    async function load() {
      try {
        const data = await loadChampion(champion);
        if (cancelled) return;
        setError(null);
        setResult({
          championName: names[champion],
          opponentName: names[opponent],
          lane: lane,
          matchup: lookup(data.matchups, lane, opponent),      // null if no games yet
          personal: lookup(data.personal, lane, opponent),     // null if you never played it
          items: data.items,
          matchupItems: lookup(data.matchup_items, lane, opponent) || [],
        });
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [index, champion, opponent, lane]); // eslint-disable-line react-hooks/exhaustive-deps

  function swapChampions() {
    setChampion(opponent);
    setOpponent(champion);
  }

  const champions = index ? index.champions : [];
  const version = index ? index.ddragon_version : null;

  return (
    <div className="dashboard">
      <header className="topbar">
        <div className="title">
          <h1>LoL Matchup Analytics</h1>
          <p>Bayesian-shrunk win rates. Every number shows how much data backs it.</p>
        </div>
        <div className="pickers">
          <select value={champion} onChange={(e) => setChampion(e.target.value)} aria-label="Your champion">
            {champions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button className="icon-button" onClick={swapChampions} title="Swap champions" aria-label="Swap champions">
            ⇄
          </button>
          <select value={opponent} onChange={(e) => setOpponent(e.target.value)} aria-label="Opponent">
            {champions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select value={lane} onChange={(e) => setLane(e.target.value)} aria-label="Lane">
            {LANES.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </select>
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      {result && (
        <>
          <section className="kpis">
            {result.matchup ? (
              <Tile
                label={`${result.championName} vs ${result.opponentName} · ${laneLabel(result.lane)}`}
                value={pct(result.matchup.shrunk_winrate)}
                sub={`Raw ${pct(result.matchup.raw_winrate)} over ${result.matchup.games} games, ` +
                     `shrunk toward a ${pct(result.matchup.prior)} lane baseline`}
              >
                <ConfidenceBadge level={result.matchup.confidence} />
              </Tile>
            ) : (
              <Tile
                label={`${result.championName} vs ${result.opponentName} · ${laneLabel(result.lane)}`}
                value="–" sub="No games yet for this matchup in this lane."
              />
            )}

            {result.personal ? (
              <Tile
                label="Your record"
                value={pct(result.personal.shrunk_winrate)}
                sub={`${result.personal.games} games (raw ${pct(result.personal.raw_winrate)}) ` +
                     `vs population ${pct(result.personal.population_winrate)}`}
              />
            ) : (
              <Tile label="Your record" value="–" sub="You haven't played this matchup yet." />
            )}

            {result.personal ? (
              <Tile label="Your edge" value={signedPct(result.personal.edge)} sub={result.personal.verdict} />
            ) : (
              <Tile label="Your edge" value="–" sub="Needs games of your own." />
            )}

            {index && (
              <Tile
                label="Data behind this"
                small
                value={`${index.match_count.toLocaleString()} matches`}
                sub={`Prior strength fitted from the data: k = ${index.k_lane} for lanes, ` +
                     `${index.k_matchup} for matchups. Personal and items use k = ${index.k}.`}
              />
            )}
          </section>

          <section className="row">
            <div className="panel">
              <h2>Items vs {result.opponentName}</h2>
              <p className="caption">
                Edge vs the same item in {result.championName}'s other games. Matchup samples are
                small, so these are shrunk hard.
              </p>
              {result.matchupItems.length > 0 ? (
                <ItemTable list={result.matchupItems} edgeLabel="Edge vs usual" version={version} />
              ) : (
                <p className="empty">Not enough item data for this matchup yet.</p>
              )}
            </div>

            <div className="panel">
              <h2>Top items for {result.championName}</h2>
              <p className="caption">
                All matchups. Edge compares games with the item to similar games (same length, same
                number of finished items). An association, not proof the item causes wins.
              </p>
              {result.items.length > 0 ? (
                <ItemTable list={result.items} edgeLabel="Edge" version={version} />
              ) : (
                <p className="empty">Not enough item data for this champion yet.</p>
              )}
            </div>
          </section>

          <section className="row">
            <div className="panel">
              <h2>Shrinkage: raw vs. corrected</h2>
              <p className="caption">
                Items vs {result.opponentName}, fewest games at the top (game count in brackets).
                The longer the line, the harder a small sample was pulled in.
              </p>
              {result.matchupItems.length > 0 ? (
                <ShrinkageChart items={result.matchupItems} />
              ) : (
                <p className="empty">No items to chart for this matchup yet.</p>
              )}
            </div>

            {/* a new key for each matchup starts the panel fresh, clearing the old summary */}
            <CoachPanel key={`${champion}-${opponent}-${lane}`} result={result} />
          </section>
        </>
      )}

      {index && (
        <footer className="footer">
          {index.match_count.toLocaleString()} ranked matches from {index.first_game} to {index.last_game} ·
          patch {index.ddragon_version} · updated {index.built_at}
        </footer>
      )}
    </div>
  );
}
