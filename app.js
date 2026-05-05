// ─── Particle network animation ──────────────────────────────────────────────
(function () {
  const canvas = document.getElementById("particleCanvas");
  const ctx = canvas.getContext("2d");

  const CONFIG = {
    count: 90,
    maxDist: 140,       // max distance to draw a line between particles
    mouseDist: 180,     // mouse influence radius
    speed: 0.45,
    dotRadius: 2.2,
    lineWidth: 1,
    color: "108,99,255",   // RGB of accent
    colorAlt: "0,212,255", // RGB of accent-2
  };

  let W = 0, H = 0;
  const mouse = { x: -9999, y: -9999 };
  let particles = [];

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function rand(min, max) { return Math.random() * (max - min) + min; }

  function createParticles() {
    particles = [];
    for (let i = 0; i < CONFIG.count; i++) {
      particles.push({
        x: rand(0, W),
        y: rand(0, H),
        vx: rand(-CONFIG.speed, CONFIG.speed),
        vy: rand(-CONFIG.speed, CONFIG.speed),
      });
    }
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);

    // update positions
    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;
    }

    // draw lines between particles
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < CONFIG.maxDist) {
          const alpha = (1 - dist / CONFIG.maxDist) * 0.35;
          ctx.beginPath();
          ctx.strokeStyle = `rgba(${CONFIG.color},${alpha})`;
          ctx.lineWidth = CONFIG.lineWidth;
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }

    // draw lines to mouse
    for (const p of particles) {
      const dx = p.x - mouse.x;
      const dy = p.y - mouse.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < CONFIG.mouseDist) {
        const alpha = (1 - dist / CONFIG.mouseDist) * 0.7;
        ctx.beginPath();
        ctx.strokeStyle = `rgba(${CONFIG.colorAlt},${alpha})`;
        ctx.lineWidth = CONFIG.lineWidth * 1.4;
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(mouse.x, mouse.y);
        ctx.stroke();
      }
    }

    // draw dots
    for (const p of particles) {
      const dx = p.x - mouse.x;
      const dy = p.y - mouse.y;
      const near = Math.sqrt(dx * dx + dy * dy) < CONFIG.mouseDist;
      ctx.beginPath();
      ctx.arc(p.x, p.y, CONFIG.dotRadius, 0, Math.PI * 2);
      ctx.fillStyle = near
        ? `rgba(${CONFIG.colorAlt},0.9)`
        : `rgba(${CONFIG.color},0.7)`;
      ctx.fill();
    }

    requestAnimationFrame(draw);
  }

  window.addEventListener("mousemove", (e) => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  });
  window.addEventListener("mouseleave", () => {
    mouse.x = -9999;
    mouse.y = -9999;
  });

  window.addEventListener("resize", () => {
    resize();
    createParticles();
  });

  resize();
  createParticles();
  draw();
})();

// ─────────────────────────────────────────────────────────────────────────────

const sampleQuestions = [];  // kept for semantic tab compat

const genreEl = document.getElementById("filterGenre");

// Custom select logic
(function () {
  const trigger = genreEl.querySelector(".custom-select__trigger");
  const list = genreEl.querySelector(".custom-select__list");
  const label = genreEl.querySelector(".custom-select__label");

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    genreEl.classList.toggle("open");
  });

  list.addEventListener("click", (e) => {
    const li = e.target.closest("li");
    if (!li) return;
    genreEl.dataset.value = li.dataset.value;
    label.textContent = li.textContent;
    list.querySelectorAll("li").forEach(el => el.classList.remove("selected"));
    li.classList.add("selected");
    genreEl.classList.remove("open");
  });

  document.addEventListener("click", () => genreEl.classList.remove("open"));
})();

const el = {
  genre: genreEl,
  yearFrom: document.getElementById("filterYearFrom"),
  yearTo: document.getElementById("filterYearTo"),
  rating: document.getElementById("filterRating"),
  ratingValue: document.getElementById("ratingValue"),
  sort: document.getElementById("filterSort"),
  run: document.getElementById("runBtn"),
  clear: document.getElementById("clearBtn"),
  loadMore: document.getElementById("loadMoreBtn"),
  status: document.getElementById("statusText"),
  sqlCards: document.getElementById("sqlCards")
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
  if (el.genre.dataset.value) params.genre = el.genre.dataset.value;
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
      (r) => `<div class="movie-card" data-movie-id="${r.movieId}">
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
      (r) => `<div class="movie-card" data-movie-id="${r.movieId}">
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
    el.status.textContent = `Done · ${filterSummary(params)}`;
    el.clear.hidden = false;
    el.loadMore.hidden = !out.has_more;
    sqlCurrentPage = out.page;
  } catch (e) {
    if (page === 1) renderMovieCards([], el.sqlCards);
    el.status.textContent = `Error: ${e.message}`;
    el.clear.hidden = false;
  } finally {
    el.run.disabled = false;
  }
}

el.run.addEventListener("click", () => runQuery(1));
el.loadMore.addEventListener("click", () => runQuery(sqlCurrentPage + 1));
el.clear.addEventListener("click", () => {
  el.genre.dataset.value = "";
  el.genre.querySelector(".custom-select__label").textContent = "Any genre";
  el.genre.querySelectorAll("li").forEach(li => li.classList.remove("selected"));
  el.yearFrom.value = "";
  el.yearTo.value = "";
  el.rating.value = 0;
  el.rating.style.setProperty("--pct", "0%");
  el.ratingValue.textContent = "any";
  el.sort.value = "popular";
  el.sqlCards.innerHTML = "";
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

// auto-resize textarea
semEl.input.addEventListener("input", () => {
  semEl.input.style.height = "auto";
  semEl.input.style.height = semEl.input.scrollHeight + "px";
});

// Enter submits, Shift+Enter adds newline
semEl.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    runSemanticSearch(1);
  }
});
semEl.loadMore.addEventListener("click", () => runSemanticSearch(semCurrentPage + 1));
semEl.clear.addEventListener("click", () => {
  semEl.input.value = "";
  semEl.cards.innerHTML = "";
  semEl.status.textContent = "Ready";
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

// ─── Movie detail modal ───────────────────────────────────────────────────────

const movieModal = document.getElementById("movieModal");
const movieModalInner = movieModal.querySelector(".modal__inner");
const movieModalClose = document.getElementById("modalClose");

function openMovieModal(movieId) {
  movieModalInner.innerHTML = `<p class="modal__loading">Loading…</p>`;
  movieModal.hidden = false;
  document.body.style.overflow = "hidden";

  fetch(`/api/movies/${encodeURIComponent(movieId)}`)
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((d) => {
      const poster = d.poster_url || POSTER_PLACEHOLDER;
      const year = d.release_date ? `${d.release_date}` : "";
      const runtime = d.runtime ? `${d.runtime} min` : "";
      const rating = d.tmdb_rating ? `★ ${d.tmdb_rating.toFixed(1)}` : "";
      const genres = (d.genres || "").replace(/\|/g, " · ");
      const chips = [year, genres, runtime, rating]
        .filter(Boolean)
        .map((c) => `<span class="modal__meta-chip">${escHtml(c)}</span>`)
        .join("");
      const tagline = d.plot ? `<p class="modal__tagline">${escHtml(d.plot)}</p>` : "";
      const desc = d.description
        ? `<p class="modal__desc">${escHtml(d.description)}</p>`
        : "";
      const tmdbLink = d.tmdbId
        ? `<a class="modal__link modal__link--tmdb" href="https://www.themoviedb.org/movie/${encodeURIComponent(d.tmdbId)}" target="_blank" rel="noopener noreferrer">TMDB</a>`
        : "";
      const imdbLink = d.imdbId
        ? `<a class="modal__link modal__link--imdb" href="https://www.imdb.com/title/${encodeURIComponent(d.imdbId)}" target="_blank" rel="noopener noreferrer">IMDb</a>`
        : "";
      const providersHtml = (() => {
        const list = d.watch_providers;
        if (!list || list.length === 0) return "";
        const items = list
          .map((p) =>
            p.logo_url
              ? `<a class="modal__provider" href="${escHtml(p.url || "#")}" target="_blank" rel="noopener noreferrer" title="${escHtml(p.provider_name)}"><img src="${escHtml(p.logo_url)}" alt="${escHtml(p.provider_name)}" /></a>`
              : `<a class="modal__provider modal__provider--text" href="${escHtml(p.url || "#")}" target="_blank" rel="noopener noreferrer">${escHtml(p.provider_name)}</a>`
          )
          .join("");
        return `<div class="modal__providers"><span class="modal__providers-label">Gdzie obejrzeć</span><div class="modal__providers-list">${items}</div></div>`;
      })();
      movieModalInner.innerHTML = `
        <img class="modal__poster" src="${escHtml(poster)}" alt="${escHtml(d.title)}" onerror="this.src='${POSTER_PLACEHOLDER}'" />
        <div class="modal__details">
          <h2 id="modalTitle" class="modal__title">${escHtml(d.title)}</h2>
          <p class="modal__meta">${chips}</p>
          ${tagline}
          ${desc}
          ${providersHtml}
          <div class="modal__links">${tmdbLink}${imdbLink}</div>
        </div>`;
    })
    .catch(() => {
      movieModalInner.innerHTML = `<p class="modal__loading">Could not load movie details.</p>`;
    });
}

function closeMovieModal() {
  movieModal.hidden = true;
  document.body.style.overflow = "";
}

movieModalClose.addEventListener("click", closeMovieModal);
movieModal.addEventListener("click", (e) => {
  if (e.target === movieModal) closeMovieModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !movieModal.hidden) closeMovieModal();
});

document.addEventListener("click", (e) => {
  const card = e.target.closest(".movie-card[data-movie-id]");
  if (!card) return;
  openMovieModal(card.dataset.movieId);
});
