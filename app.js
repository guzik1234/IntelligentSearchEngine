const sampleQuestions = [
  "Which users rated the highest number of distinct movies?",
  "Show movies with the highest number of unique tags.",
  "Which tags appear most frequently in the dataset?",
  "Which movies have many ratings but few tags?",
  "How did the number of submitted ratings change year over year?"
];

const el = {
  samples: document.getElementById("sampleQuestions"),
  input: document.getElementById("questionInput"),
  run: document.getElementById("runBtn"),
  status: document.getElementById("statusText"),
  sql: document.getElementById("sqlOutput"),
  head: document.getElementById("resultHead"),
  body: document.getElementById("resultBody"),
  insight: document.getElementById("insightText"),
  chart: document.getElementById("chartCanvas")
};

function renderSamples() {
  sampleQuestions.forEach((q) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = q;
    b.onclick = () => {
      el.input.value = q;
      el.input.focus();
    };
    el.samples.appendChild(b);
  });
}

function renderTable(columns = [], rows = []) {
  el.head.innerHTML = `<tr>${columns.map((c) => `<th>${c}</th>`).join("")}</tr>`;

  if (!rows.length) {
    el.body.innerHTML = `<tr><td colspan="${Math.max(columns.length, 1)}">No data returned for this question.</td></tr>`;
    return;
  }

  el.body.innerHTML = rows
    .map((r) => `<tr>${r.map((v) => `<td>${v}</td>`).join("")}</tr>`)
    .join("");
}

function renderChart(rows = []) {
  if (typeof Plotly === "undefined") return;

  const labels = rows.map((r) => String(r[0]));
  const values = rows.map((r) => Number(r[1]) || 0);
  const short = labels.map((t) => (t.length > 34 ? `${t.slice(0, 31)}...` : t));
  const h = rows.length ? Math.min(460, Math.max(240, rows.length * 34)) : 220;

  el.chart.style.height = `${h}px`;

  const layout = {
    autosize: false,
    height: h,
    margin: { t: 14, r: 12, b: 30, l: 160 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(255,253,248,0.6)",
    font: { family: "IBM Plex Mono, monospace", size: 11, color: "#332a25" },
    xaxis: { color: "#5d524a", gridcolor: "rgba(216,202,183,0.35)" },
    yaxis: { automargin: true, color: "#5d524a" },
    annotations: rows.length
      ? []
      : [{ text: "No data to plot", x: 0.5, y: 0.5, showarrow: false, xref: "paper", yref: "paper" }]
  };

  const data = rows.length
    ? [
        {
          type: "bar",
          orientation: "h",
          x: values,
          y: short,
          customdata: labels,
          marker: { color: values, colorscale: [[0, "#86d5c9"], [1, "#0b7a75"]] },
          hovertemplate: "%{customdata}<br>Value: %{x}<extra></extra>"
        }
      ]
    : [];

  Plotly.react(el.chart, data, layout, { responsive: true, displayModeBar: false });
}

function fallback(question) {
  return {
    sql: "No SQL generated (API unavailable).",
    columns: [],
    rows: [],
    insight: "The API is unavailable right now. Please try again in a moment."
  };
}

async function runQuery() {
  const question = el.input.value.trim();
  if (!question) return (el.status.textContent = "Enter a question first.");

  el.run.disabled = true;
  el.status.textContent = "Generating SQL and insight...";

  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });

    if (!res.ok) throw new Error(`API error (${res.status})`);
    const out = await res.json();

    el.sql.textContent = out.sql;
    renderTable(out.columns, out.rows);
    renderChart(out.rows);
    el.insight.textContent = out.insight;
    el.status.textContent = `Done (source: ${out.source || "api"})`;
  } catch (e) {
    const out = fallback(question);
    el.sql.textContent = out.sql;
    renderTable(out.columns, out.rows);
    renderChart(out.rows);
    el.insight.textContent = out.insight;
    el.status.textContent = `Done (fallback): ${e.message}`;
  } finally {
    el.run.disabled = false;
  }
}

el.run.addEventListener("click", runQuery);
renderSamples();
el.input.value = sampleQuestions[0];
runQuery();

// ─── Semantic Search ─────────────────────────────────────────────────────────

const semEl = {
  input: document.getElementById("semanticInput"),
  btn: document.getElementById("semanticBtn"),
  status: document.getElementById("semanticStatus"),
  head: document.getElementById("semanticHead"),
  body: document.getElementById("semanticBody")
};

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderSemanticResults(results) {
  semEl.head.innerHTML =
    "<tr><th>#</th><th>Title</th><th>Genres</th><th>Match</th><th>Description</th></tr>";

  if (!results.length) {
    semEl.body.innerHTML = "<tr><td colspan='5'>No results found.</td></tr>";
    return;
  }

  semEl.body.innerHTML = results
    .map(
      (r, i) => `<tr>
        <td>${i + 1}</td>
        <td>${escHtml(r.title)}</td>
        <td>${escHtml((r.genres || "").replace(/\|/g, ", "))}</td>
        <td>${(r.score * 100).toFixed(1)}%</td>
        <td class="cell--desc">${escHtml(r.description || r.plot || "—")}</td>
      </tr>`
    )
    .join("");
}

async function runSemanticSearch() {
  const query = semEl.input.value.trim();
  if (!query) return (semEl.status.textContent = "Enter a description first.");

  semEl.btn.disabled = true;
  semEl.status.textContent = "Searching… (first run may take 1–2 min to build embeddings)";

  try {
    const res = await fetch("/api/semantic-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: 10 })
    });

    if (!res.ok) throw new Error(`API error (${res.status})`);
    const out = await res.json();
    renderSemanticResults(out.results);
    semEl.status.textContent = `Found ${out.total} matching movies`;
  } catch (e) {
    semEl.status.textContent = `Error: ${e.message}`;
  } finally {
    semEl.btn.disabled = false;
  }
}

semEl.btn.addEventListener("click", runSemanticSearch);

// ─── Tab switching ────────────────────────────────────────────────────────────

function switchTab(name) {
  const sqlPane = document.getElementById("paneSql");
  const semPane = document.getElementById("paneSemantic");
  const sqlTab = document.getElementById("tabSql");
  const semTab = document.getElementById("tabSemantic");

  const isSql = name === "sql";
  sqlPane.hidden = !isSql;
  semPane.hidden = isSql;
  sqlTab.classList.toggle("tab--active", isSql);
  semTab.classList.toggle("tab--active", !isSql);
  sqlTab.setAttribute("aria-selected", String(isSql));
  semTab.setAttribute("aria-selected", String(!isSql));
}

document.getElementById("tabSql").addEventListener("click", () => switchTab("sql"));
document.getElementById("tabSemantic").addEventListener("click", () => switchTab("semantic"));
