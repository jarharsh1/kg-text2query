// Minimal UI for the Text-to-Query Knowledge-Graph QA API.
// Talks to the same origin that serves this page: GET /health, POST /ask.
// The differentiator: it renders the GENERATED QUERY AST, prominently.

const chat = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("q");
const sendBtn = document.getElementById("send");

function addMessage(text, who) {
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

// Render the generated query AST as an open <details> — this is the selling point.
function addQuery(container, query) {
  const d = document.createElement("details");
  d.className = "query";
  d.open = true;
  const s = document.createElement("summary");
  if (!query) {
    s.textContent = "No query could be formed";
    d.appendChild(s);
    container.appendChild(d);
    return;
  }
  const hops = (query.hops || [])
    .map((h) => `${h.relation}(${h.direction})`)
    .join(" → ");
  s.textContent = `Generated query: ${query.start_type}`
    + (query.start_name ? `["${query.start_name}"]` : "")
    + (hops ? ` → ${hops}` : "")
    + ` → ${query.result_type}`;
  d.appendChild(s);
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(query, null, 2);
  d.appendChild(pre);
  container.appendChild(d);
}

function addResults(container, results) {
  const d = document.createElement("details");
  d.className = "results";
  const s = document.createElement("summary");
  s.textContent = `${results.length} result(s)`;
  d.appendChild(s);
  const ul = document.createElement("ul");
  for (const r of results) {
    const li = document.createElement("li");
    li.textContent = `${r.name} (${r.type})`;
    ul.appendChild(li);
  }
  d.appendChild(ul);
  container.appendChild(d);
}

async function ask(question) {
  addMessage(question, "user");
  input.value = "";
  sendBtn.disabled = true;
  const bot = addMessage("…", "bot");
  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    bot.textContent = data.answer || "(no answer)";
    addQuery(bot, data.query);
    if (data.results && data.results.length) addResults(bot, data.results);
  } catch (err) {
    bot.textContent = `Error: ${err.message}`;
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (q) ask(q);
});

document.getElementById("examples").addEventListener("click", (e) => {
  if (e.target.tagName === "BUTTON") ask(e.target.textContent);
});

// Populate the health pills on load.
fetch("/health")
  .then((r) => r.json())
  .then((h) => {
    document.getElementById("backend").textContent = `backend: ${h.backend}`;
    document.getElementById("nodes").textContent = `graph: ${h.graph_nodes} nodes`;
  })
  .catch(() => {});
