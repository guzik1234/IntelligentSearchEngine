const sampleQuestions = [
  "Which genre had the highest watch time in Q4?",
  "How did churn change between Q3 and Q4?",
  "Which movies have the highest completion rate?",
  "What is the average rating by genre?",
  "Which user segment shows the best retention?"
];

const API_BASE_URL = "";

const sampleContainer = document.getElementById("sampleQuestions");
const questionInput = document.getElementById("questionInput");
const runBtn = document.getElementById("runBtn");
const statusText = document.getElementById("statusText");
const sqlOutput = document.getElementById("sqlOutput");
const resultHead = document.getElementById("resultHead");
const resultBody = document.getElementById("resultBody");
const insightText = document.getElementById("insightText");
const chartContainer = document.getElementById("chartCanvas");
let currentRows = [];

function renderSampleQuestions() {
  sampleQuestions.forEach((question) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = question;
    button.addEventListener("click", () => {
      questionInput.value = question;
      questionInput.focus();
    });
    sampleContainer.appendChild(button);
  });
}

function renderTable(columns, rows) {
  resultHead.innerHTML = "";
  resultBody.innerHTML = "";

  const headRow = document.createElement("tr");
  columns.forEach((column) => {
    const th = document.createElement("th");
    th.textContent = column;
    headRow.appendChild(th);
  });
  resultHead.appendChild(headRow);

  if (!rows || rows.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.textContent = "No data returned for this question.";
    td.colSpan = Math.max(columns.length, 1);
    tr.appendChild(td);
    resultBody.appendChild(tr);
    return;
  }

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    row.forEach((value) => {
      const td = document.createElement("td");
      td.textContent = value;
      tr.appendChild(td);
    });
    resultBody.appendChild(tr);
  });
}

function drawBarChart(rows) {
  if (typeof Plotly === "undefined") {
    statusText.textContent = "Plotly is not loaded.";
    return;
  }

  if (!rows || rows.length === 0) {
    const emptyHeight = 220;
    chartContainer.style.height = `${emptyHeight}px`;
    Plotly.react(
      chartContainer,
      [],
      {
        autosize: false,
        height: emptyHeight,
        margin: { t: 12, r: 12, b: 28, l: 36 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        annotations: [
          {
            text: "No data to plot",
            x: 0.5,
            y: 0.5,
            showarrow: false,
            font: { family: "Space Grotesk, sans-serif", size: 14, color: "#5d524a" },
            xref: "paper",
            yref: "paper"
          }
        ],
        xaxis: { visible: false },
        yaxis: { visible: false }
      },
      { responsive: true, displayModeBar: false }
    );
    return;
  }

  const labels = rows.map((row) => row[0]);
  const values = rows.map((row) => row[1]);
  const shortLabels = labels.map((label) => {
    const text = String(label);
    return text.length > 34 ? `${text.slice(0, 31)}...` : text;
  });

  // Dynamic height keeps labels readable and avoids overflow in dense results.
  const chartHeight = Math.min(520, Math.max(240, rows.length * 38));
  chartContainer.style.height = `${chartHeight}px`;

  const trace = {
    x: values,
    y: shortLabels,
    type: "bar",
    orientation: "h",
    marker: {
      color: values,
      colorscale: [
        [0, "#86d5c9"],
        [1, "#0b7a75"]
      ],
      line: { color: "#085956", width: 1 }
    },
    customdata: labels,
    hovertemplate: "%{customdata}<br>Value: %{x}<extra></extra>",
    cliponaxis: true
  };

  const layout = {
    autosize: false,
    height: chartHeight,
    margin: { t: 14, r: 16, b: 34, l: 160 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(255,253,248,0.6)",
    xaxis: {
      title: { text: "Value" },
      color: "#5d524a",
      gridcolor: "rgba(216,202,183,0.35)"
    },
    yaxis: {
      automargin: true,
      color: "#5d524a",
      zerolinecolor: "rgba(216,202,183,0.5)",
      gridcolor: "rgba(216,202,183,0.35)"
    },
    bargap: 0.2,
    font: { family: "IBM Plex Mono, monospace", size: 11, color: "#332a25" }
  };

  Plotly.react(chartContainer, [trace], layout, {
    responsive: true,
    displayModeBar: false
  });
}

function buildKeywordFromQuestion(question) {
  const stopWords = new Set([
    "which",
    "what",
    "how",
    "did",
    "does",
    "have",
    "has",
    "had",
    "the",
    "a",
    "an",
    "is",
    "are",
    "in",
    "on",
    "for",
    "to",
    "and",
    "of",
    "between",
    "by",
    "q3",
    "q4"
  ]);

  const words = question
    .toLowerCase()
    .split(/\s+/)
    .map((word) => word.replace(/[^a-z0-9-]/g, ""))
    .filter((word) => word && !stopWords.has(word) && word.length > 2);

  if (words.length === 0) {
    return "movie";
  }

  return words.slice(0, 3).join(" ");
}

function buildFallbackResponse(question) {
  const keyword = buildKeywordFromQuestion(question);

  return {
    sql: `SELECT m.title, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(*) AS rating_count\nFROM ratings r\nJOIN movies m ON m.movieId = r.movieId\nWHERE m.title LIKE '%${keyword.replaceAll("'", "''")}%'\nGROUP BY m.movieId, m.title\nORDER BY rating_count DESC, avg_rating DESC\nLIMIT 8;`,
    columns: ["title", "avg_rating", "rating_count"],
    rows: [
      [`${keyword} sample 1`, 4.2, 180],
      [`${keyword} sample 2`, 4.0, 132],
      [`${keyword} sample 3`, 3.8, 95],
      [`${keyword} sample 4`, 3.6, 71]
    ],
    insight: `API is currently unavailable, so this is a local preview generated for keyword '${keyword}'.`,
    source: "fallback"
  };
}

function renderResult(response, statusLabel) {
  sqlOutput.textContent = response.sql;
  renderTable(response.columns, response.rows);
  currentRows = response.rows;
  drawBarChart(currentRows);
  insightText.textContent = response.insight;
  statusText.textContent = statusLabel;
}

async function runQuery() {
  const question = questionInput.value.trim();
  if (!question) {
    statusText.textContent = "Enter a question first.";
    return;
  }

  statusText.textContent = "Generating SQL and insight...";
  runBtn.disabled = true;

  try {
    const response = await fetch(`${API_BASE_URL}/api/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ question })
    });

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      const errorMessage = errorPayload?.detail || `API error (${response.status})`;
      throw new Error(errorMessage);
    }

    const payload = await response.json();
    renderResult(payload, `Done (source: ${payload.source || "api"})`);
  } catch (error) {
    const fallback = buildFallbackResponse(question);
    renderResult(fallback, `Done (fallback): ${error.message}`);
  } finally {
    runBtn.disabled = false;
  }
}

runBtn.addEventListener("click", runQuery);
window.addEventListener("resize", () => {
  if (typeof Plotly !== "undefined") {
    Plotly.Plots.resize(chartContainer);
  }
});

renderSampleQuestions();
questionInput.value = sampleQuestions[0];
runQuery();
