// The AI coaching summary. Runs in your browser with your own Anthropic key,
// so the site needs no server. The prompt is built only from computed stats.
import Anthropic from "@anthropic-ai/sdk";

// current Haiku: fast and cheap, plenty for a 3-4 sentence summary
const MODEL = "claude-haiku-5-5";

function pct(x) {
  return (x * 100).toFixed(1) + "%";
}

function signedPct(x) {
  const sign = x >= 0 ? "+" : "";
  return sign + (x * 100).toFixed(1) + "%";
}

// Turn the numbers on screen into plain sentences for the prompt.
export function buildFacts(champName, oppName, lane, matchup, personal, items, matchupItems) {
  const facts = [];
  facts.push(`Matchup: ${champName} vs ${oppName} in ${lane}.`);
  facts.push(
    `Population shrunk win rate for ${champName}: ${pct(matchup.shrunk_winrate)} over ${matchup.games} games.`
  );

  if (personal) {
    facts.push(
      `This player's personal record: ${pct(personal.shrunk_winrate)} shrunk win rate ` +
        `over ${personal.games} games vs population ${pct(personal.population_winrate)} ` +
        `(edge ${signedPct(personal.edge)}).`
    );
  } else {
    facts.push("This player has not played this matchup.");
  }

  // champion-wide items with large samples (the list is already sorted best edge first)
  const reliable = [];
  for (const it of items) {
    if (it.games >= 20 && reliable.length < 4) {
      reliable.push(`${it.item} (${signedPct(it.edge)}, ${it.games} games)`);
    }
  }
  if (reliable.length > 0) {
    facts.push("Champion-wide highest-edge items (large samples, reliable): " + reliable.join(", "));
  }

  // items into this opponent specifically (small samples)
  const speculative = [];
  for (const it of matchupItems) {
    if (speculative.length < 4) {
      speculative.push(`${it.item} (${signedPct(it.edge)} vs general build, only ${it.games} games)`);
    }
  }
  if (speculative.length > 0) {
    facts.push(
      `Items that trend well specifically into ${oppName} (SMALL samples, less certain): ` +
        speculative.join(", ")
    );
  } else {
    facts.push(`Not enough matchup-specific item data vs ${oppName} to say anything reliable.`);
  }

  return facts;
}

// Ask Claude for the summary. Throws the SDK's typed errors on failure.
export async function getCoachingSummary(apiKey, facts) {
  // dangerouslyAllowBrowser: the SDK refuses to run in a browser unless told to,
  // because a key in a web page can leak. Here it is your own key in your own browser.
  const client = new Anthropic({ apiKey: apiKey, dangerouslyAllowBrowser: true });

  const prompt =
    "You are a League of Legends coaching assistant. Using ONLY the statistics below, write a " +
    "direct 3-4 sentence summary for the player. Cover: (1) how they perform in this matchup vs " +
    "the baseline, (2) their most reliable item choices (the champion-wide, large-sample ones), " +
    "and (3) any items that trend well specifically into this opponent. CRITICAL: when you cite " +
    "a small-sample number, explicitly note it is based on few games and therefore uncertain. " +
    "Distinguish reliable (large-sample) advice from speculative (small-sample) advice. Do NOT " +
    "invent champion abilities, strategy, or any facts not in the statistics.\n\n" +
    facts.join("\n");

  const response = await client.messages.create({
    model: MODEL,
    max_tokens: 2000,
    output_config: { effort: "low" }, // a short summary needs little thinking
    messages: [{ role: "user", content: prompt }],
  });

  if (response.stop_reason === "refusal") {
    return "Claude declined to write a summary for this one.";
  }

  let text = "";
  for (const block of response.content) {
    if (block.type === "text") {
      text += block.text;
    }
  }
  return text;
}

// Plain-words message for an error from getCoachingSummary.
export function describeError(err) {
  if (err instanceof Anthropic.AuthenticationError) {
    return "That API key was rejected. Check it and save it again.";
  }
  if (err instanceof Anthropic.RateLimitError) {
    return "Rate limited by Anthropic. Wait a minute and try again.";
  }
  if (err instanceof Anthropic.APIConnectionError) {
    return "Could not reach Anthropic. Check your internet connection.";
  }
  if (err instanceof Anthropic.APIError) {
    return `Anthropic API error: ${err.message}`;
  }
  return `Something went wrong: ${err.message}`;
}
