import asyncio
import json
import os
import re
from urllib import request
from typing import Final

SYSTEM_PROMPT_HEADER: Final[str] = """You are a SQL generation agent for analytics.
Return ONLY one SQL query with no explanation, no markdown, no code block.
Rules:
- Generate only read-only SQL (SELECT only).
- Never use INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, EXEC, CALL, MERGE.
- Embed all filter values directly in the SQL using actual values from the question.
- Do not use named parameters, placeholders, or example strings like :keyword or GenreName.
- Use SQLite syntax: use LIKE (not ILIKE), use strftime for dates.
- There is NO users table; userId is a column in ratings and tags.
- Use m.title for movie title searches, m.genres for genre searches.
- Prefer clear aliases and add LIMIT when listing many rows."""

FORBIDDEN_SQL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|exec|call|merge)\b",
    flags=re.IGNORECASE,
)
COMMENT_PATTERN: Final[re.Pattern[str]] = re.compile(r"(--|/\*|\*/)")
TABLE_REF_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b(from|join)\s+([a-zA-Z_][\w]*)", re.IGNORECASE)
CTE_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?:\bwith\b|,)\s*([a-zA-Z_][\w]*)\s+as\s*\(", re.IGNORECASE)
LIMIT_PATTERN: Final[re.Pattern[str]] = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)
DEFAULT_LIMIT: Final[int] = 50
MAX_LIMIT: Final[int] = 200
ALLOWED_TABLES: Final[set[str]] = {"movies", "ratings", "tags", "links", "users"}

DEFAULT_OLLAMA_URL: Final[str] = "http://127.0.0.1:11434/api/generate"
DEFAULT_OLLAMA_MODEL: Final[str] = "sqlcoder:7b"
DEFAULT_GROQ_MODEL: Final[str] = "llama-3.3-70b-versatile"


class SQLAgent:
    def __init__(self) -> None:
        self.groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.groq_model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL
        self.ollama_url = os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL).strip()
        self.ollama_model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL
        self.schema_context = (
            "- movies(movieId, title, genres)\n"
            "- ratings(userId, movieId, rating, timestamp)\n"
            "- tags(userId, movieId, tag, timestamp)\n"
            "- links(movieId, imdbId, tmdbId)"
        )

    def set_schema_context(self, schema_context: str) -> None:
        if schema_context.strip():
            self.schema_context = schema_context.strip()

    def _is_select_only(self, sql: str) -> bool:
        s = sql.strip().rstrip(";")
        lowered = s.lower()
        if not (lowered.startswith("select") or lowered.startswith("with")):
            return False
        if FORBIDDEN_SQL_PATTERN.search(s):
            return False
        if ";" in s:
            return False
        return True

    def _apply_limit_guardrail(self, sql: str) -> str:
        stripped = sql.strip().rstrip(";")
        m = LIMIT_PATTERN.search(stripped)
        if not m:
            return f"{stripped}\nLIMIT {DEFAULT_LIMIT};"

        limit_value = int(m.group(1))
        if limit_value <= MAX_LIMIT:
            return f"{stripped};"

        limited = LIMIT_PATTERN.sub(f"LIMIT {MAX_LIMIT}", stripped, count=1)
        return f"{limited};"

    def validate_sql(self, sql: str) -> tuple[bool, str]:
        stripped = sql.strip()
        if not stripped:
            return False, "empty-sql"
        if COMMENT_PATTERN.search(stripped):
            return False, "comments-not-allowed"
        if not self._is_select_only(stripped):
            return False, "not-select-only"

        head = stripped.rstrip(";")
        if ";" in head:
            return False, "multiple-statements"

        cte_names = {name.lower() for name in CTE_NAME_PATTERN.findall(stripped)}
        tables = [t.lower() for _, t in TABLE_REF_PATTERN.findall(stripped)]
        if not tables:
            return False, "no-table-reference"
        if any(t not in ALLOWED_TABLES and t not in cte_names for t in tables):
            return False, "table-not-allowed"

        return True, "ok"

    def _extract_sql_block(self, text: str) -> str:
        # Try to find the first SELECT or WITH statement, skipping any preamble
        # (sqlcoder sometimes prepends <s>, #, or other tokens)
        sql_match = re.search(r"((?:SELECT|WITH)\b.*)", text, flags=re.IGNORECASE | re.DOTALL)
        if sql_match:
            cleaned = sql_match.group(1)
        else:
            # fallback: markdown code block
            md_match = re.search(r"```sql\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
            if md_match:
                cleaned = md_match.group(1)
            else:
                cleaned = text
        # strip trailing format markers like [/SQL], [QUESTION], etc.
        cleaned = re.sub(r"\s*\[/?[A-Z][^\]]*\].*$", "", cleaned, flags=re.DOTALL).strip()
        # normalize Postgres-isms that break SQLite
        cleaned = re.sub(r"\bilike\b", "LIKE", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+NULLS\s+(?:LAST|FIRST)\b", "", cleaned, flags=re.IGNORECASE)
        # 'genre' is not a valid column (the column is 'genres'); always safe to rename
        cleaned = re.sub(r"\bgenre\b", "genres", cleaned, flags=re.IGNORECASE)
        return cleaned

    def _generate_with_groq(self, question: str) -> str:
        from groq import Groq  # type: ignore[import-untyped]

        client = Groq(api_key=self.groq_api_key)
        user_prompt = f"""### Task
Generate a SQL query to answer: {question}

### Database Schema
The query will run on a SQLite database with the following schema:
{self.schema_context}

### Schema Hints
-- movies.title = full movie name (e.g. 'Toy Story (1995)')
-- movies.genres = pipe-separated genre categories (e.g. 'Comedy|Drama')
-- There is no separate genres table; always use movies.genres column
-- Standard join: ratings r JOIN movies m ON r.movieId = m.movieId
-- userId is available as ratings.userId (no separate users table needed)

Return ONLY the SQL query, nothing else."""

        response = client.chat.completions.create(
            model=self.groq_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_HEADER},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            max_tokens=512,
        )
        return self._extract_sql_block(response.choices[0].message.content or "")

    def _generate_with_ollama(self, question: str) -> str:
        prompt = f"""### Task
Generate a SQL query to answer [QUESTION]{question}[/QUESTION]

### Database Schema
The query will run on a SQLite database with the following schema:
{self.schema_context}

### Rules
{SYSTEM_PROMPT_HEADER}

### Schema Hints
-- movies.title = full movie name (e.g. 'Toy Story (1995)')
-- movies.genres = pipe-separated genre categories (e.g. 'Comedy|Drama')
-- There is no separate genres table; always use movies.genres column
-- Standard join: ratings r JOIN movies m ON r.movieId = m.movieId
-- userId is available as ratings.userId (no separate users table needed)

### Answer
Given the database schema, here is the SQL query that answers [QUESTION]{question}[/QUESTION]:
"""
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.ollama_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=25) as res:
            body = json.loads(res.read().decode("utf-8"))
        return self._extract_sql_block(body.get("response", ""))

    async def generate_tmdb_params(self, question: str) -> tuple[dict, str]:
        """Convert natural language question to TMDB discover/search parameters."""
        if self.groq_api_key:
            try:
                params = await asyncio.to_thread(self._extract_tmdb_params_with_groq, question)
                return params, f"groq:{self.groq_model}"
            except Exception:
                pass
        return {"keyword": question}, "fallback"

    async def extract_search_keyword(self, description: str) -> str:
        """Extract a concise TMDB-friendly keyword from a natural language movie description."""
        if self.groq_api_key:
            try:
                keyword = await asyncio.to_thread(self._keyword_from_description_with_groq, description)
                if keyword:
                    return keyword
            except Exception:
                pass
        # fallback: take first 5 words
        return " ".join(description.split()[:5])

    def _keyword_from_description_with_groq(self, description: str) -> str:
        from groq import Groq  # type: ignore[import-untyped]

        client = Groq(api_key=self.groq_api_key)
        response = client.chat.completions.create(
            model=self.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "The user describes a movie plot or theme. "
                        "Your job: return the BEST 1-2 word search term to find this movie on TMDB. "
                        "Rules:\n"
                        "- If the description clearly matches a famous movie, return its exact title (e.g. 'Toy Story').\n"
                        "- Otherwise return 1-2 key nouns from the plot (e.g. 'toys', 'space robot', 'wizard school').\n"
                        "- NEVER return genre words like 'adventure', 'fantasy', 'drama'.\n"
                        "- Return ONLY the keyword string, nothing else."
                    ),
                },
                {"role": "user", "content": description},
            ],
            temperature=0,
            max_tokens=20,
        )
        return (response.choices[0].message.content or "").strip().strip('"').strip("'")

    def _extract_tmdb_params_with_groq(self, question: str) -> dict:
        from groq import Groq  # type: ignore[import-untyped]

        client = Groq(api_key=self.groq_api_key)
        response = client.chat.completions.create(
            model=self.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract movie/TV search parameters from a natural language question. "
                        "Return ONLY a valid JSON object with these optional fields:\n"
                        '- "similar_to": string — title when user asks for similar/related/like a specific title '
                        '(e.g. "films similar to Forrest Gump" → {"similar_to": "Forrest Gump"}).\n'
                        '- "actor": string — full name of actor, actress or director when user asks for their movies '
                        '(e.g. "movies with Tom Hanks", "films starring Scarlett Johansson", "directed by Nolan" → {"actor": "Tom Hanks"}).\n'
                        '- "theme": string — specific theme, motif or plot element when user describes a concept '
                        '(e.g. "movies about time travel", "films with heist", "coming of age stories", '
                        '"movies about AI", "survival in space" → {"theme": "time travel"}).\n'
                        '- "plot_description": string — free-form plot summary when user describes a specific plot '
                        '(e.g. "a movie where a man wakes up in a different body" → {"plot_description": "man wakes up different body"}). '
                        "Use this for vague descriptions that don't fit theme or keyword.\n"
                        '- "genre": one of: action, adventure, animation, comedy, crime, '
                        "documentary, drama, family, fantasy, history, horror, music, mystery, "
                        "romance, science fiction, thriller, war, western\n"
                        '- "year": integer (specific release year)\n'
                        '- "year_gte": integer (released from this year)\n'
                        '- "year_lte": integer (released up to this year)\n'
                        '- "min_rating": float 1-10\n'
                        '- "sort_by": one of: popular, rating, newest, oldest, revenue\n'
                        '- "keyword": string — only for direct title searches (NOT for actor/similar/theme/plot requests)\n'
                        "Priority: similar_to > actor > theme > plot_description > keyword.\n"
                        "Return ONLY JSON, no explanation."
                    ),
                },
                {"role": "user", "content": question},
            ],
            temperature=0,
            max_tokens=200,
        )
        text = response.choices[0].message.content or "{}"
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}

    async def suggest_movies_for_plot(self, description: str) -> list[str]:
        """Ask Groq to suggest specific movie titles matching a plot description."""
        if self.groq_api_key:
            try:
                titles = await asyncio.to_thread(self._suggest_titles_with_groq, description)
                if titles:
                    return titles
            except Exception:
                pass
        return []

    def _suggest_titles_with_groq(self, description: str) -> list[str]:
        from groq import Groq  # type: ignore[import-untyped]

        client = Groq(api_key=self.groq_api_key)
        response = client.chat.completions.create(
            model=self.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "The user describes a movie plot or scenario. "
                        "Your job: return a JSON array of exactly 10 real movie titles "
                        "that best match this description. Include both classic and modern films. "
                        "Order by how well they match (best first). "
                        "Return ONLY a valid JSON array of strings, e.g.: "
                        '["Big", "Freaky Friday", "Vice Versa"]. '
                        "No explanations, no markdown."
                    ),
                },
                {"role": "user", "content": description},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        text = (response.choices[0].message.content or "").strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                titles = json.loads(match.group())
                return [t for t in titles if isinstance(t, str)][:10]
            except Exception:
                pass
        return []

    async def rerank_with_groq(self, question: str, candidates: list[dict]) -> list[dict]:
        """Re-rank TMDB candidates using Groq based on semantic relevance to the query."""
        if not self.groq_api_key or len(candidates) < 3:
            return candidates
        try:
            return await asyncio.to_thread(self._rerank_with_groq, question, candidates)
        except Exception:
            return candidates

    def _rerank_with_groq(self, question: str, candidates: list[dict]) -> list[dict]:
        from groq import Groq  # type: ignore[import-untyped]

        items = []
        for m in candidates:
            title = m.get("title", "")
            desc = (m.get("description") or "")[:120]
            items.append(f"[ID:{m['movieId']}] {title} — {desc}")
        movies_list = "\n".join(items)

        client = Groq(api_key=self.groq_api_key)
        response = client.chat.completions.create(
            model=self.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a movie recommendation expert. "
                        "Given a user query and a list of movies (each with an ID), "
                        "return a JSON array of the movie IDs ordered from most to least relevant to the query. "
                        "Only include IDs of movies that genuinely match the query. "
                        "Return up to 20 IDs. "
                        "Return ONLY a valid JSON array of integers, e.g.: [123, 456, 789]. "
                        "No explanations, no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Query: {question}\n\nMovies:\n{movies_list}",
                },
            ],
            temperature=0,
            max_tokens=400,
        )
        text = (response.choices[0].message.content or "").strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                ids = json.loads(match.group())
                id_to_movie = {m["movieId"]: m for m in candidates}
                ranked = [id_to_movie[mid] for mid in ids if mid in id_to_movie]
                ranked_ids = {m["movieId"] for m in ranked}
                return ranked + [m for m in candidates if m["movieId"] not in ranked_ids]
            except Exception:
                pass
        return candidates

    async def generate_sql(self, question: str) -> tuple[str, str]:
        # Prefer Groq when API key is configured
        if self.groq_api_key:
            try:
                sql = await asyncio.to_thread(self._generate_with_groq, question)
                source = f"groq:{self.groq_model}"
            except Exception:
                return "", "groq-error"
        else:
            # Fallback to Ollama
            try:
                sql = self._generate_with_ollama(question)
                source = f"ollama:{self.ollama_model}"
            except Exception:
                return "", "ollama-unavailable"

        if not sql.strip():
            return "", f"{source}+empty-response"

        is_valid, reason = self.validate_sql(sql)
        if not is_valid:
            return "", f"{source}+invalid-sql:{reason}"

        sql = self._apply_limit_guardrail(sql)
        return sql, source
