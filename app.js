const sampleQuestions = [
  "Which genre had the highest watch time in Q4?",
  "How did churn change between Q3 and Q4?",
  "Which movies have the highest completion rate?",
  "What is the average rating by genre?",
  "Which user segment shows the best retention?"
];

const mockResponse = {
  sql: `SELECT genre,
       SUM(watch_minutes) AS total_watch_minutes,
       ROUND(AVG(rating), 2) AS avg_rating
FROM fact_watch_events e
JOIN dim_movies m ON m.movie_id = e.movie_id
WHERE e.quarter = 'Q4'
GROUP BY genre
ORDER BY total_watch_minutes DESC
LIMIT 5;`,
  columns: ["genre", "total_watch_minutes", "avg_rating"],
  rows: [
    ["Drama", 152340, 4.32],
    ["Sci-Fi", 141220, 4.18],
    ["Comedy", 118905, 3.91],
    ["Thriller", 103880, 4.07],
    ["Animation", 98420, 4.24]
  ],
  insight:
    "Drama generated the highest watch time in Q4, leading Sci-Fi by about 7.9%. Both genres also maintain strong average ratings above 4.1, suggesting a high-engagement and high-satisfaction segment."
};

const sampleContainer = document.getElementById("sampleQuestions");
const questionInput = document.getElementById("questionInput");
const runBtn = document.getElementById("runBtn");
const statusText = document.getElementById("statusText");
const sqlOutput = document.getElementById("sqlOutput");
const resultHead = document.getElementById("resultHead");
const resultBody = document.getElementById("resultBody");
const insightText = document.getElementById("insightText");
const canvas = document.getElementById("chartCanvas");
const ctx = canvas.getContext("2d");

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
  const labels = rows.map((row) => row[0]);
  const values = rows.map((row) => row[1]);

  const width = canvas.width;
  const height = canvas.height;
  const margin = { top: 26, right: 20, bottom: 56, left: 52 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const maxValue = Math.max(...values) * 1.1;
  const barWidth = chartWidth / values.length - 18;

  ctx.clearRect(0, 0, width, height);

  ctx.strokeStyle = "#d7c8b4";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(margin.left, margin.top);
  ctx.lineTo(margin.left, margin.top + chartHeight);
  ctx.lineTo(margin.left + chartWidth, margin.top + chartHeight);
  ctx.stroke();

  ctx.font = "12px IBM Plex Mono";
  ctx.fillStyle = "#6a5c51";

  for (let i = 0; i <= 4; i += 1) {
    const yValue = (maxValue / 4) * i;
    const y = margin.top + chartHeight - (yValue / maxValue) * chartHeight;

    ctx.strokeStyle = "#efe2cf";
    ctx.beginPath();
    ctx.moveTo(margin.left, y);
    ctx.lineTo(margin.left + chartWidth, y);
    ctx.stroke();

    ctx.fillText(Math.round(yValue).toString(), 8, y + 3);
  }

  values.forEach((value, index) => {
    const x = margin.left + index * (barWidth + 18) + 10;
    const barHeight = (value / maxValue) * chartHeight;
    const y = margin.top + chartHeight - barHeight;

    const gradient = ctx.createLinearGradient(0, y, 0, y + barHeight);
    gradient.addColorStop(0, "#0b7a75");
    gradient.addColorStop(1, "#5ac0b0");

    ctx.fillStyle = gradient;
    ctx.fillRect(x, y, barWidth, barHeight);

    ctx.fillStyle = "#2f2722";
    ctx.textAlign = "center";
    ctx.fillText(labels[index], x + barWidth / 2, margin.top + chartHeight + 18);
    ctx.fillText(value.toString(), x + barWidth / 2, y - 6);
  });
}

function fakeRunQuery() {
  const question = questionInput.value.trim();
  if (!question) {
    statusText.textContent = "Enter a question first.";
    return;
  }

  statusText.textContent = "Generating SQL and insight...";
  runBtn.disabled = true;

  // Simulated latency for frontend MVP without backend.
  setTimeout(() => {
    sqlOutput.textContent = mockResponse.sql;
    renderTable(mockResponse.columns, mockResponse.rows);
    drawBarChart(mockResponse.rows);
    insightText.textContent = mockResponse.insight;

    statusText.textContent = "Done";
    runBtn.disabled = false;
  }, 650);
}

runBtn.addEventListener("click", fakeRunQuery);
window.addEventListener("resize", () => drawBarChart(mockResponse.rows));

renderSampleQuestions();
questionInput.value = sampleQuestions[0];
fakeRunQuery();
