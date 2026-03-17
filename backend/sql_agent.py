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



class SQLAgent:
    def __init__(self) -> None:
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

    def _build_system_prompt(self) -> str:
        return f"{SYSTEM_PROMPT_HEADER}\nSchema context:\n{self.schema_context}"

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

    def _generate_with_ollama(self, question: str) -> str:
        prompt = (
            f"### Task\n"
            f"Generate a SQL query to answer [QUESTION]{question}[/QUESTION]\n\n"
            f"### Database Schema\n"
            f"The query will run on a SQLite database with the following schema:\n"
            f"{self.schema_context}\n\n"
            f"### Rules\n"
            f"{SYSTEM_PROMPT_HEADER}\n\n"
            f"### Schema Hints\n"
            f"-- movies.title = full movie name (e.g. 'Toy Story (1995)')\n"
            f"-- movies.genres = pipe-separated genre categories (e.g. 'Comedy|Drama')\n"
            f"-- There is no separate genres table; always use movies.genres column\n"
            f"-- Standard join: ratings r JOIN movies m ON r.movieId = m.movieId\n"
            f"-- userId is available as ratings.userId (no separate users table needed)\n\n"
            f"### Answer\n"
            f"Given the database schema, here is the SQL query that answers "
            f"[QUESTION]{question}[/QUESTION]:\n\n"
        )
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

    async def generate_sql(self, question: str) -> tuple[str, str, str]:
        try:
            sql = self._generate_with_ollama(question)
            source = f"ollama:{self.ollama_model}"
        except Exception:
            return "", "", "ollama-unavailable"

        if not sql.strip():
            return "", "", f"ollama:{self.ollama_model}+empty-response"

        is_valid, reason = self.validate_sql(sql)
        if not is_valid:
            return "", "", f"ollama:{self.ollama_model}+invalid-sql:{reason}"

        sql = self._apply_limit_guardrail(sql)
        return sql, "", source
