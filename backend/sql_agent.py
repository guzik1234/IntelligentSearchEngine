import re
from typing import Final

SYSTEM_PROMPT: Final[str] = """You are a SQL generation agent for analytics.
Return ONLY one SQL query.
Rules:
- Generate only read-only SQL (SELECT only).
- Never use INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, EXEC, CALL, MERGE.
- Prefer clear aliases and LIMIT when listing rows.
Schema context:
- movies(movieId, title, genres)
- ratings(userId, movieId, rating, timestamp)
- tags(userId, movieId, tag, timestamp)
- links(movieId, imdbId, tmdbId)
If question is movie-title search, use:
    SELECT m.title, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(*) AS rating_count
    FROM ratings r
    JOIN movies m ON m.movieId = r.movieId
    WHERE m.title LIKE '%' || :keyword || '%'
    GROUP BY m.movieId, m.title
    ORDER BY rating_count DESC, avg_rating DESC
    LIMIT 8;
"""

FORBIDDEN_SQL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|exec|call|merge)\b",
    flags=re.IGNORECASE,
)


class SQLAgent:
    def __init__(self) -> None:
        pass

    def _extract_keyword(self, question: str) -> str:
        stop_words = {
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
            "q4",
        }
        words = [w.strip("?,.!:;\"'()[]{}") for w in question.lower().split()]
        filtered = [w for w in words if w and w not in stop_words and len(w) > 2]
        if not filtered:
            return "movie"
        return " ".join(filtered[:3])

    def _template_sql(self, question: str) -> str:
        q = question.lower()

        if "average rating" in q and "genre" in q:
            return (
                "SELECT m.genres AS genre, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(*) AS rating_count\n"
                "FROM ratings r\n"
                "JOIN movies m ON m.movieId = r.movieId\n"
                "GROUP BY m.genres\n"
                "ORDER BY avg_rating DESC;"
            )

        if "churn" in q and ("q3" in q or "q4" in q):
            return (
                "SELECT quarter, active_users\n"
                "FROM (\n"
                "  SELECT\n"
                "    strftime('%Y', datetime(r.timestamp, 'unixepoch')) || '-Q' ||\n"
                "    ((CAST(strftime('%m', datetime(r.timestamp, 'unixepoch')) AS INTEGER) - 1) / 3 + 1) AS quarter,\n"
                "    COUNT(DISTINCT r.userId) AS active_users\n"
                "  FROM ratings r\n"
                "  GROUP BY quarter\n"
                ") q\n"
                "WHERE quarter LIKE '%Q3' OR quarter LIKE '%Q4'\n"
                "ORDER BY quarter DESC\n"
                "LIMIT 8;"
            )

        if "completion rate" in q or ("highest" in q and "completion" in q):
            return (
                "SELECT m.title, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(*) AS rating_count\n"
                "FROM ratings r\n"
                "JOIN movies m ON m.movieId = r.movieId\n"
                "GROUP BY m.movieId, m.title\n"
                "ORDER BY avg_rating DESC, rating_count DESC\n"
                "LIMIT 10;"
            )

        if "retention" in q and "segment" in q:
            return (
                "SELECT activity_bucket, COUNT(*) AS users\n"
                "FROM (\n"
                "  SELECT userId,\n"
                "    CASE\n"
                "      WHEN COUNT(*) >= 200 THEN 'high_activity'\n"
                "      WHEN COUNT(*) >= 50 THEN 'mid_activity'\n"
                "      ELSE 'low_activity'\n"
                "    END AS activity_bucket\n"
                "  FROM ratings\n"
                "  GROUP BY userId\n"
                ") u\n"
                "GROUP BY activity_bucket\n"
                "ORDER BY users DESC;"
            )

        if "watch time" in q and "genre" in q:
            return (
                "SELECT m.genres AS genre, COUNT(*) * 120 AS estimated_watch_minutes\n"
                "FROM ratings r\n"
                "JOIN movies m ON m.movieId = r.movieId\n"
                "GROUP BY m.genres\n"
                "ORDER BY estimated_watch_minutes DESC\n"
                "LIMIT 10;"
            )

        return (
            "SELECT m.title, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(*) AS rating_count\n"
            "FROM ratings r\n"
            "JOIN movies m ON m.movieId = r.movieId\n"
            "WHERE m.title LIKE '%' || :keyword || '%'\n"
            "GROUP BY m.movieId, m.title\n"
            "ORDER BY rating_count DESC, avg_rating DESC\n"
            "LIMIT 8;"
        )

    def _is_select_only(self, sql: str) -> bool:
        s = sql.strip().rstrip(";")
        if not s.lower().startswith("select"):
            return False
        if FORBIDDEN_SQL_PATTERN.search(s):
            return False
        if ";" in s:
            return False
        return True

    async def generate_sql(self, question: str) -> tuple[str, str, str]:
        keyword = self._extract_keyword(question)

        sql = self._template_sql(question)
        if not self._is_select_only(sql):
            sql = (
                "SELECT m.title, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(*) AS rating_count\n"
                "FROM ratings r\n"
                "JOIN movies m ON m.movieId = r.movieId\n"
                "WHERE m.title LIKE '%' || :keyword || '%'\n"
                "GROUP BY m.movieId, m.title\n"
                "ORDER BY rating_count DESC, avg_rating DESC\n"
                "LIMIT 8;"
            )
        return sql, keyword, "template"
