from fastapi.testclient import TestClient

import backend.main as main


client = TestClient(main.app)


def test_health_endpoint() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["db"].endswith("movielens.db")


def test_analytics_top_genres_endpoint() -> None:
    response = client.get("/api/analytics/top-genres?limit=5")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "sqlite+pandas+numpy"
    assert payload["columns"] == ["genre", "avg_rating", "rating_count"]
    assert len(payload["rows"]) <= 5


def test_search_blocks_invalid_sql(monkeypatch) -> None:
    async def fake_generate_sql(_: str):
        return "SELECT * FROM unknown_table", "movie", "test"

    monkeypatch.setattr(main.sql_agent, "generate_sql", fake_generate_sql)

    response = client.post("/api/search", json={"question": "anything"})
    assert response.status_code == 400
    assert "Blocked by SQL validator" in response.json()["detail"]


def test_search_returns_rows_for_valid_sql(monkeypatch) -> None:
    async def fake_generate_sql(_: str):
        return (
            "SELECT m.title, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(*) AS rating_count "
            "FROM ratings r JOIN movies m ON m.movieId = r.movieId "
            "WHERE m.title LIKE '%' || :keyword || '%' "
            "GROUP BY m.movieId, m.title ORDER BY rating_count DESC LIMIT 5;",
            "matrix",
            "test",
        )

    monkeypatch.setattr(main.sql_agent, "generate_sql", fake_generate_sql)

    response = client.post("/api/search", json={"question": "matrix"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["safe"] is True
    assert payload["source"].startswith("sqlite+sql-agent:test")
    assert len(payload["rows"]) > 0


def test_search_returns_message_for_no_intent_match(monkeypatch) -> None:
    async def fake_generate_sql(_: str):
        return "", "movie", "template+no-intent-match"

    monkeypatch.setattr(main.sql_agent, "generate_sql", fake_generate_sql)

    response = client.post("/api/search", json={"question": "some random unrelated request"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["sql"] == "No SQL generated for this question."
    assert payload["rows"] == []
    assert payload["columns"] == []
    assert "could not confidently map" in payload["insight"]
