import asyncio

from backend.sql_agent import SQLAgent


def test_validate_sql_accepts_simple_select() -> None:
    agent = SQLAgent()
    ok, reason = agent.validate_sql("SELECT * FROM ratings LIMIT 10;")
    assert ok is True
    assert reason == "ok"


def test_validate_sql_rejects_comments_and_multi_statement() -> None:
    agent = SQLAgent()

    ok_comment, reason_comment = agent.validate_sql("SELECT * FROM ratings -- comment")
    assert ok_comment is False
    assert reason_comment == "comments-not-allowed"

    ok_multi, reason_multi = agent.validate_sql("SELECT * FROM ratings; DROP TABLE movies;")
    assert ok_multi is False
    assert reason_multi == "not-select-only"


def test_validate_sql_rejects_unknown_table() -> None:
    agent = SQLAgent()
    ok, reason = agent.validate_sql("SELECT * FROM unknown_table LIMIT 10;")
    assert ok is False
    assert reason == "table-not-allowed"


def test_validate_sql_accepts_with_cte_on_allowed_tables() -> None:
    agent = SQLAgent()
    sql = (
        "WITH top_users AS ("
        "SELECT userId, COUNT(*) AS c FROM ratings GROUP BY userId"
        ") "
        "SELECT userId, c FROM top_users ORDER BY c DESC LIMIT 10;"
    )
    ok, reason = agent.validate_sql(sql)
    assert ok is True
    assert reason == "ok"


def test_limit_guardrail_adds_and_caps_limit() -> None:
    agent = SQLAgent()

    no_limit = "SELECT * FROM ratings"
    with_limit = agent._apply_limit_guardrail(no_limit)
    assert "LIMIT 50" in with_limit

    too_big = "SELECT * FROM ratings LIMIT 9999;"
    capped = agent._apply_limit_guardrail(too_big)
    assert "LIMIT 200" in capped


def test_generate_sql_falls_back_to_template_when_model_unavailable() -> None:
    agent = SQLAgent()

    def fail_generate(_: str) -> str:
        raise RuntimeError("model unavailable")

    agent._generate_with_ollama = fail_generate  # type: ignore[method-assign]

    sql, keyword, source = asyncio.run(agent.generate_sql("What is the average rating by genre?"))

    assert "GROUP BY m.genres" in sql
    assert keyword == "genre"
    assert source.startswith("template")


def test_generate_sql_uses_semantic_fallback_for_non_rule_prompt() -> None:
    agent = SQLAgent()

    def fail_generate(_: str) -> str:
        raise RuntimeError("model unavailable")

    agent._generate_with_ollama = fail_generate  # type: ignore[method-assign]

    sql, keyword, source = asyncio.run(
        agent.generate_sql("Which users rated the highest number of distinct movies?")
    )

    assert "COUNT(DISTINCT r.movieId)" in sql
    assert "FROM ratings r" in sql
    assert source.startswith("template")
    assert keyword == "number distinct"


def test_generate_sql_handles_most_rated_without_title_like_fallback() -> None:
    agent = SQLAgent()

    def fail_generate(_: str) -> str:
        raise RuntimeError("model unavailable")

    agent._generate_with_ollama = fail_generate  # type: ignore[method-assign]

    sql, _keyword, _source = asyncio.run(agent.generate_sql("Show the top 20 most-rated movies."))

    assert "COUNT(*) AS rating_count" in sql
    assert "ORDER BY rating_count DESC" in sql
    assert "WHERE m.title LIKE" not in sql
