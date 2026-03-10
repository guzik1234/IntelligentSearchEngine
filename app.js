const sampleQuestions = [
  "Which genre had the highest watch time in Q4?",
  "How did churn change between Q3 and Q4?",
  "Which movies have the highest completion rate?",
  "What is the average rating by genre?",
  "Which user segment shows the best retention?"
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
  const key = (question.toLowerCase().match(/[a-z0-9-]{3,}/g) || ["movie"]).slice(0, 2).join(" ");
  const safe = key.replaceAll("'", "''");
  return {
    sql: `SELECT m.title, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(*) AS rating_count\nFROM ratings r\nJOIN movies m ON m.movieId = r.movieId\nWHERE m.title LIKE '%${safe}%'\nGROUP BY m.movieId, m.title\nORDER BY rating_count DESC, avg_rating DESC\nLIMIT 8;`,
    columns: ["title", "avg_rating", "rating_count"],
    rows: [[`${key} sample 1`, 4.2, 180], [`${key} sample 2`, 4, 132], [`${key} sample 3`, 3.8, 95]],
    insight: `Fallback preview for keyword '${key}'.`,
    source: "fallback"
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
