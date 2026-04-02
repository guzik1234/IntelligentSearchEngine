import csv
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.analytics import top_genres_from_sqlite
from backend.semantic_search import SemanticSearchEngine
from backend.sql_agent import SQLAgent

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ml-latest-small"
DB_DIR = PROJECT_ROOT / "data" / "db"
DB_PATH = DB_DIR / "movielens.db"
ASSET_FILES = {"app.js", "styles.css"}


class SearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300)


class SearchResponse(BaseModel):
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    insight: str
    safe: bool
    source: str


class AnalyticsResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    insight: str
    source: str


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)


class SemanticSearchResult(BaseModel):
    movieId: int
    title: str
    genres: str
    description: str | None
    plot: str | None
    score: float


class SemanticSearchResponse(BaseModel):
    results: list[SemanticSearchResult]
    query: str
    total: int


app = FastAPI(title="IntelligentSearchEngine API", version="0.1.0")
sql_agent = SQLAgent()
semantic_engine = SemanticSearchEngine()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_insight(rows: list[list[Any]], question: str) -> str:
    if not rows:
        return f"No results found for: '{question}'. Try rephrasing your question."

    first_row = rows[0]
    return f"Returned {len(rows)} rows. First row sample: {first_row}."


def _ensure_views(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE VIEW IF NOT EXISTS users AS "
        "SELECT DISTINCT userId, userId AS username FROM ratings"
    )


def _ensure_database() -> None:
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            _ensure_views(conn)
        return

    if not RAW_DIR.exists():
        raise RuntimeError(
            f"MovieLens raw data not found at '{RAW_DIR}'. Download/extract dataset first."
        )

    DB_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        def insert_from_csv(csv_name: str, sql: str, row_builder) -> None:
            with open(RAW_DIR / csv_name, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                cur.executemany(sql, (row_builder(r) for r in reader))

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS movies (
                movieId INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                genres TEXT NOT NULL,
                description TEXT,
                plot TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ratings (
                userId INTEGER NOT NULL,
                movieId INTEGER NOT NULL,
                rating REAL NOT NULL,
                timestamp INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                userId INTEGER NOT NULL,
                movieId INTEGER NOT NULL,
                tag TEXT,
                timestamp INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS links (
                movieId INTEGER PRIMARY KEY,
                imdbId TEXT,
                tmdbId TEXT
            )
            """
        )

        insert_from_csv(
            "movies.csv",
            "INSERT INTO movies(movieId, title, genres, description, plot) VALUES (?, ?, ?, ?, ?)",
            lambda r: (int(r["movieId"]), r["title"], r["genres"], r.get("description") or None, r.get("plot") or None),
        )
        insert_from_csv(
            "ratings.csv",
            "INSERT INTO ratings(userId, movieId, rating, timestamp) VALUES (?, ?, ?, ?)",
            lambda r: (int(r["userId"]), int(r["movieId"]), float(r["rating"]), int(r["timestamp"])),
        )
        insert_from_csv(
            "tags.csv",
            "INSERT INTO tags(userId, movieId, tag, timestamp) VALUES (?, ?, ?, ?)",
            lambda r: (int(r["userId"]), int(r["movieId"]), r.get("tag", ""), int(r["timestamp"])),
        )
        insert_from_csv(
            "links.csv",
            "INSERT INTO links(movieId, imdbId, tmdbId) VALUES (?, ?, ?)",
            lambda r: (int(r["movieId"]), r.get("imdbId", ""), r.get("tmdbId", "")),
        )

        cur.execute("CREATE INDEX IF NOT EXISTS idx_ratings_movieId ON ratings(movieId)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ratings_userId ON ratings(userId)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title)")
        _ensure_views(conn)


def _run_sql(sql: str) -> tuple[list[str], list[list[Any]]]:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchmany(50)
        columns = [d[0] for d in cur.description] if cur.description else []
    return columns, [list(r) for r in rows]


def _schema_context_from_db() -> str:
    ddl_lines: list[str] = []
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        for (sql,) in cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall():
            if sql:
                ddl_lines.append(sql.strip() + ";")
    return "\n\n".join(ddl_lines)


_ensure_database()
sql_agent.set_schema_context(_schema_context_from_db())


@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "index.html")


@app.get("/{asset_name}")
def frontend_assets(asset_name: str) -> FileResponse:
    if asset_name not in ASSET_FILES:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(PROJECT_ROOT / asset_name)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "db": str(DB_PATH)}


@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    sql, sql_source = await sql_agent.generate_sql(request.question)

    if not sql.strip():
        return SearchResponse(
            sql="No SQL generated for this question.",
            columns=[],
            rows=[],
            insight=(
                "I could not confidently map this question to the current dataset schema. "
                "Try rephrasing with terms like ratings, tags, genres, users, or time trend."
            ),
            safe=True,
            source=f"sqlite+sql-agent:{sql_source}",
        )

    try:
        columns, rows = _run_sql(sql)
    except sqlite3.Error as exc:
        return SearchResponse(
            sql=sql,
            columns=[],
            rows=[],
            insight=f"The AI generated a valid query but it failed during execution: {exc}. Try rephrasing your question.",
            safe=True,
            source=f"sqlite+sql-agent:{sql_source}+exec-error",
        )

    insight = _build_insight(rows, request.question)

    return SearchResponse(
        sql=sql,
        columns=columns,
        rows=rows,
        insight=insight,
        safe=True,
        source=f"sqlite+sql-agent:{sql_source}",
    )


@app.post("/api/semantic-search", response_model=SemanticSearchResponse)
async def semantic_search(request: SemanticSearchRequest) -> SemanticSearchResponse:
    await semantic_engine.ensure_loaded(DB_PATH)
    results = semantic_engine.search(request.query, top_k=request.top_k)
    return SemanticSearchResponse(
        results=results,
        query=request.query,
        total=len(results),
    )


@app.get("/api/analytics/top-genres", response_model=AnalyticsResponse)
def analytics_top_genres(limit: int = 10) -> AnalyticsResponse:
    safe_limit = min(max(limit, 1), 30)
    columns, rows, insight = top_genres_from_sqlite(DB_PATH, safe_limit)
    return AnalyticsResponse(
        columns=columns,
        rows=rows,
        insight=insight,
        source="sqlite+pandas+numpy",
    )
