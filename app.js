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

function renderTable(columns = [], rows = [], posters = {}) {
  el.head.innerHTML = `<tr>${columns.map((c) => `<th>${c}</th>`).join("")}</tr>`;

  if (!rows.length) {
    el.body.innerHTML = `<tr><td colspan="${Math.max(columns.length, 1)}">No data returned for this question.</td></tr>`;
    return;
  }

  const midIdx = columns.indexOf("movieId");

  el.body.innerHTML = rows
    .map((r) => {
      const cells = r.map((v, i) => {
        if (i === midIdx && posters[v]) {
          return `<td><img class="table-poster" src="${escHtml(posters[v])}" alt="poster" loading="lazy"></td>`;
        }
        return `<td>${v}</td>`;
      }).join("");
      return `<tr>${cells}</tr>`;
    })
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
    renderTable(out.columns, out.rows, out.posters || {});
    renderChart(out.rows);
    el.insight.textContent = out.insight;
    el.status.textContent = `Done (source: ${out.source || "api"})`;
  } catch (e) {
    const out = fallback(question);
    el.sql.textContent = out.sql;
    renderTable(out.columns, out.rows, {});
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
  cards: document.getElementById("semanticCards")
};

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const POSTER_PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='240' viewBox='0 0 160 240'%3E%3Crect width='160' height='240' fill='%23efe5d6'/%3E%3Ctext x='80' y='125' text-anchor='middle' fill='%235d524a' font-size='13' font-family='sans-serif'%3ENo poster%3C/text%3E%3C/svg%3E";

function renderSemanticResults(results) {
  if (!results.length) {
    semEl.cards.innerHTML = "<p class='no-results'>No results found.</p>";
    return;
  }

  semEl.cards.innerHTML = results
    .map(
      (r) => `<div class="movie-card">
        <img
          class="movie-card__poster"
          src="${r.poster_url ? escHtml(r.poster_url) : POSTER_PLACEHOLDER}"
          alt="${escHtml(r.title)}"
          loading="lazy"
          onerror="this.src='${POSTER_PLACEHOLDER}'"
        />
        <div class="movie-card__body">
          <p class="movie-card__title">${escHtml(r.title)}</p>
          <p class="movie-card__genres">${escHtml((r.genres || "").replace(/\|/g, " · "))}</p>
          <p class="movie-card__score">${(r.score * 100).toFixed(1)}% match</p>
          <p class="movie-card__desc">${escHtml(r.description || r.plot || "")}</p>
        </div>
      </div>`
    )
    .join("");
}

async function runSemanticSearch() {
  const query = semEl.input.value.trim();
  if (!query) return (semEl.status.textContent = "Enter a description first.");

  semEl.btn.disabled = true;
  semEl.status.textContent = "Searching\u2026 (first run may take 1\u20132 min to build embeddings)";

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
