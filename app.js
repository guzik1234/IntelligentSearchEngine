const sampleQuestions = [];  // kept for semantic tab compat

const el = {
  genre: document.getElementById("filterGenre"),
  yearFrom: document.getElementById("filterYearFrom"),
  yearTo: document.getElementById("filterYearTo"),
  rating: document.getElementById("filterRating"),
  ratingValue: document.getElementById("ratingValue"),
  sort: document.getElementById("filterSort"),
  run: document.getElementById("runBtn"),
  clear: document.getElementById("clearBtn"),
  loadMore: document.getElementById("loadMoreBtn"),
  status: document.getElementById("statusText"),
  sqlCards: document.getElementById("sqlCards"),
  insight: document.getElementById("insightText")
};

let sqlCurrentPage = 1;
let sqlLastParams = {};

el.rating.addEventListener("input", () => {
  const v = parseFloat(el.rating.value);
  el.ratingValue.textContent = v === 0 ? "any" : `${v}+`;
  // fill the range track visually
  const pct = (v / parseFloat(el.rating.max)) * 100;
  el.rating.style.setProperty("--pct", `${pct}%`);
});

function readFilters() {
  const params = {};
  if (el.genre.value) params.genre = el.genre.value;
  const yFrom = parseInt(el.yearFrom.value);
  const yTo   = parseInt(el.yearTo.value);
  if (!isNaN(yFrom) && yFrom >= 1900 && yFrom <= 2030) params.year_gte = yFrom;
  if (!isNaN(yTo)   && yTo   >= 1900 && yTo   <= 2030) params.year_lte = yTo;
  const rating = parseFloat(el.rating.value);
  if (rating > 0) params.min_rating = rating;
  params.sort_by = el.sort.value;
  return params;
}

function filterSummary(params) {
  const parts = [];
  if (params.genre) parts.push(params.genre.charAt(0).toUpperCase() + params.genre.slice(1));
  if (params.year_gte && params.year_lte) parts.push(`${params.year_gte}–${params.year_lte}`);
  else if (params.year_gte) parts.push(`from ${params.year_gte}`);
  else if (params.year_lte) parts.push(`up to ${params.year_lte}`);
  if (params.min_rating) parts.push(`rated ${params.min_rating}+`);
  const sortLabels = { popular: "Most Popular", rating: "Highest Rated", newest: "Newest", oldest: "Oldest", revenue: "Box Office" };
  parts.push(sortLabels[params.sort_by] || params.sort_by);
  return parts.join(" · ");
}

const POSTER_PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='240' viewBox='0 0 160 240'%3E%3Crect width='160' height='240' fill='%23efe5d6'/%3E%3Ctext x='80' y='125' text-anchor='middle' fill='%235d524a' font-size='13' font-family='sans-serif'%3ENo poster%3C/text%3E%3C/svg%3E";

function appendMovieCards(movies, container) {
  if (!container || !movies || !movies.length) return;
  const frag = document.createDocumentFragment();
  const tmp = document.createElement("div");
  tmp.innerHTML = movies
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
          <p class="movie-card__title">${escHtml(r.title)}${
            r.release_date ? ` <span class="movie-card__year">(${escHtml(r.release_date)})</span>` : ""
          }</p>
          <p class="movie-card__genres">${escHtml((r.genres || "").replace(/\|/g, " \u00b7 "))}</p>
          ${r.tmdb_rating ? `<p class="movie-card__score">&#9733; ${r.tmdb_rating.toFixed(1)}</p>` : ""}
          <p class="movie-card__desc">${escHtml(r.description || "")}</p>
        </div>
      </div>`
    )
    .join("");
  while (tmp.firstChild) frag.appendChild(tmp.firstChild);
  container.appendChild(frag);
}

function renderMovieCards(movies, container) {
  if (!container) return;
  if (!movies || !movies.length) {
    container.innerHTML = "<p class='no-results'>No movies found.</p>";
    return;
  }
  container.innerHTML = movies
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
          <p class="movie-card__title">${escHtml(r.title)}${
            r.release_date ? ` <span class="movie-card__year">(${escHtml(r.release_date)})</span>` : ""
          }</p>
          <p class="movie-card__genres">${escHtml((r.genres || "").replace(/\|/g, " \u00b7 "))}</p>
          ${r.tmdb_rating ? `<p class="movie-card__score">&#9733; ${r.tmdb_rating.toFixed(1)}</p>` : ""}
          <p class="movie-card__desc">${escHtml(r.description || "")}</p>
        </div>
      </div>`
    )
    .join("");
}

async function runQuery(page = 1) {
  const params = page === 1 ? readFilters() : sqlLastParams;
  sqlLastParams = params;

  el.run.disabled = true;
  el.loadMore.hidden = true;
  el.status.textContent = page === 1 ? "Searching TMDB..." : "Loading more...";

  try {
    const res = await fetch("/api/filter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params, page })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `API error (${res.status})`);
    }
    const out = await res.json();

    if (page === 1) {
      renderMovieCards(out.movies || [], el.sqlCards);
    } else {
      appendMovieCards(out.movies || [], el.sqlCards);
    }
    el.insight.textContent = out.insight;
    el.status.textContent = `Done · ${filterSummary(params)}`;
    el.clear.hidden = false;
    el.loadMore.hidden = !out.has_more;
    sqlCurrentPage = out.page;
  } catch (e) {
    if (page === 1) renderMovieCards([], el.sqlCards);
    el.insight.textContent = `Error: ${e.message}`;
    el.status.textContent = `Error: ${e.message}`;
    el.clear.hidden = false;
  } finally {
    el.run.disabled = false;
  }
}

el.run.addEventListener("click", () => runQuery(1));
el.loadMore.addEventListener("click", () => runQuery(sqlCurrentPage + 1));
el.clear.addEventListener("click", () => {
  el.genre.value = "";
  el.yearFrom.value = "";
  el.yearTo.value = "";
  el.rating.value = 0;
  el.rating.style.setProperty("--pct", "0%");
  el.ratingValue.textContent = "any";
  el.sort.value = "popular";
  el.sqlCards.innerHTML = "";
  el.insight.textContent = "Insight will appear here.";
  el.status.textContent = "Ready";
  el.clear.hidden = true;
  el.loadMore.hidden = true;
  sqlCurrentPage = 1;
  sqlLastParams = {};
});

// ─── Semantic Search ─────────────────────────────────────────────────────────

const semEl = {
  input: document.getElementById("semanticInput"),
  btn: document.getElementById("semanticBtn"),
  clear: document.getElementById("semanticClearBtn"),
  loadMore: document.getElementById("semanticLoadMoreBtn"),
  status: document.getElementById("semanticStatus"),
  statusInline: document.getElementById("semanticStatusInline"),
  cards: document.getElementById("semanticCards")
};

let semCurrentPage = 1;
let semLastQuery = "";

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderSemanticResults(results) {
  renderMovieCards(results, semEl.cards);
}

async function runSemanticSearch(page = 1) {
  const query = page === 1 ? semEl.input.value.trim() : semLastQuery;
  if (!query) return (semEl.status.textContent = "Enter a description first.");

  semLastQuery = query;
  semEl.btn.disabled = true;
  semEl.loadMore.hidden = true;
  semEl.status.textContent = page === 1 ? "Searching TMDB\u2026" : "Loading more...";

  try {
    const res = await fetch("/api/semantic-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: 10, page })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `API error (${res.status})`);
    }
    const out = await res.json();
    if (page === 1) {
      renderSemanticResults(out.results);
    } else {
      appendMovieCards(out.results, semEl.cards);
    }
    semEl.status.textContent = `Found ${out.total} movies`;
    semEl.statusInline.textContent = `Found ${out.total} movies`;
    semEl.clear.hidden = false;
    semEl.loadMore.hidden = !out.has_more;
    semCurrentPage = out.page;
  } catch (e) {
    semEl.status.textContent = `Error: ${e.message}`;
  } finally {
    semEl.btn.disabled = false;
  }
}

semEl.btn.addEventListener("click", () => runSemanticSearch(1));
semEl.loadMore.addEventListener("click", () => runSemanticSearch(semCurrentPage + 1));
semEl.clear.addEventListener("click", () => {
  semEl.input.value = "";
  semEl.cards.innerHTML = "";
  semEl.status.textContent = "Ready";
  semEl.statusInline.textContent = "";
  semEl.clear.hidden = true;
  semEl.loadMore.hidden = true;
  semCurrentPage = 1;
  semLastQuery = "";
  semEl.input.focus();
});

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
