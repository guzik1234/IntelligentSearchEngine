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


def test_generate_tmdb_params_falls_back_when_groq_unavailable() -> None:
    agent = SQLAgent()
    agent.groq_api_key = ""  # disable Groq

    params, source = asyncio.run(agent.generate_tmdb_params("action movies"))

    assert source == "fallback"
    assert params.get("keyword") == "action movies"


def test_generate_tmdb_params_returns_dict_on_groq_error(monkeypatch) -> None:
    agent = SQLAgent()

    def fail_extract(_: str) -> dict:
        raise RuntimeError("groq unavailable")

    monkeypatch.setattr(agent, "_extract_tmdb_params_with_groq", fail_extract)

    params, source = asyncio.run(agent.generate_tmdb_params("horror movies 2020"))
    assert source == "fallback"
    assert isinstance(params, dict)


def test_extract_search_keyword_falls_back_without_groq() -> None:
    agent = SQLAgent()
    agent.groq_api_key = ""  # disable Groq

    keyword = asyncio.run(agent.extract_search_keyword("toys that come to life secretly"))

    # fallback: first 5 words
    assert keyword == "toys that come to life"


def test_suggest_movies_for_plot_falls_back_without_groq() -> None:
    agent = SQLAgent()
    agent.groq_api_key = ""  # disable Groq

    titles = asyncio.run(agent.suggest_movies_for_plot("a man wakes up in a different body"))

    assert titles == []


def test_suggest_movies_for_plot_parses_groq_response(monkeypatch) -> None:
    agent = SQLAgent()

    def fake_suggest(_: str) -> list[str]:
        return ["Big", "Freaky Friday", "Vice Versa"]

    monkeypatch.setattr(agent, "_suggest_titles_with_groq", fake_suggest)

    titles = asyncio.run(agent.suggest_movies_for_plot("a man wakes up in a different body"))
    assert titles == ["Big", "Freaky Friday", "Vice Versa"]


def test_suggest_movies_for_plot_handles_groq_error(monkeypatch) -> None:
    agent = SQLAgent()

    def fail(_: str) -> list[str]:
        raise RuntimeError("groq unavailable")

    monkeypatch.setattr(agent, "_suggest_titles_with_groq", fail)

    titles = asyncio.run(agent.suggest_movies_for_plot("a man wakes up in a different body"))
    assert titles == []


def test_extract_tmdb_params_detects_actor(monkeypatch) -> None:
    agent = SQLAgent()

    def fake_extract(_: str) -> dict:
        return {"actor": "Tom Hanks"}

    monkeypatch.setattr(agent, "_extract_tmdb_params_with_groq", fake_extract)

    params, source = asyncio.run(agent.generate_tmdb_params("movies with Tom Hanks"))
    assert params.get("actor") == "Tom Hanks"


def test_extract_tmdb_params_detects_similar_to(monkeypatch) -> None:
    agent = SQLAgent()

    def fake_extract(_: str) -> dict:
        return {"similar_to": "Forrest Gump"}

    monkeypatch.setattr(agent, "_extract_tmdb_params_with_groq", fake_extract)

    params, _ = asyncio.run(agent.generate_tmdb_params("films similar to Forrest Gump"))
    assert params.get("similar_to") == "Forrest Gump"


def test_extract_tmdb_params_detects_theme(monkeypatch) -> None:
    agent = SQLAgent()

    def fake_extract(_: str) -> dict:
        return {"theme": "time travel"}

    monkeypatch.setattr(agent, "_extract_tmdb_params_with_groq", fake_extract)

    params, _ = asyncio.run(agent.generate_tmdb_params("movies about time travel"))
    assert params.get("theme") == "time travel"
