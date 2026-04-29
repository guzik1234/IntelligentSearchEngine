from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.main as main

client = TestClient(main.app)

FAKE_MOVIE = {
    "movieId": 1,
    "title": "Test Movie",
    "genres": "Action",
    "description": "A test movie.",
    "poster_url": "https://image.tmdb.org/t/p/w500/test.jpg",
    "release_date": "2020",
    "tmdb_rating": 7.5,
    "score": None,
}


def test_health_endpoint() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_returns_movie_cards(monkeypatch) -> None:
    async def fake_params(_: str):
        return {"genre": "action"}, "groq:test"

    monkeypatch.setattr(main.sql_agent, "generate_tmdb_params", fake_params)
    monkeypatch.setattr(main.tmdb_search, "discover_movies", lambda params, page=1: [FAKE_MOVIE])

    response = client.post("/api/search", json={"question": "action movies"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["movies"]) == 1
    assert payload["movies"][0]["title"] == "Test Movie"
    assert payload["source"] == "tmdb+groq:test"
    assert "Found 1" in payload["insight"]


def test_search_falls_back_to_text_search_when_discover_empty(monkeypatch) -> None:
    async def fake_params(_: str):
        return {"genre": "action"}, "groq:test"

    monkeypatch.setattr(main.sql_agent, "generate_tmdb_params", fake_params)
    monkeypatch.setattr(main.tmdb_search, "discover_movies", lambda params, page=1: [])
    monkeypatch.setattr(main.tmdb_search, "search_movies", lambda query, page=1: [FAKE_MOVIE])

    response = client.post("/api/search", json={"question": "action movies"})
    assert response.status_code == 200
    assert len(response.json()["movies"]) == 1


def test_search_returns_empty_insight_when_no_results(monkeypatch) -> None:
    async def fake_params(_: str):
        return {"keyword": "xyzzy"}, "groq:test"

    monkeypatch.setattr(main.sql_agent, "generate_tmdb_params", fake_params)
    monkeypatch.setattr(main.tmdb_search, "search_movies", lambda query, page=1: [])

    response = client.post("/api/search", json={"question": "xyzzy nonexistent"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["movies"] == []
    assert "No movies found" in payload["insight"]


def test_search_rejects_too_short_question() -> None:
    response = client.post("/api/search", json={"question": "hi"})
    assert response.status_code == 422


def test_semantic_search_returns_results(monkeypatch) -> None:
    async def fake_keyword(_: str):
        return "Toy Story"

    monkeypatch.setattr(main.sql_agent, "extract_search_keyword", fake_keyword)
    monkeypatch.setattr(main.tmdb_search, "search_movies", lambda query, page=1: [FAKE_MOVIE] * 5)

    response = client.post("/api/semantic-search", json={"query": "toys come to life", "top_k": 3})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["query"] == "toys come to life"


def test_semantic_search_rejects_too_short_query() -> None:
    response = client.post("/api/semantic-search", json={"query": "hi"})
    assert response.status_code == 422


def test_movie_detail_not_found(monkeypatch) -> None:
    monkeypatch.setattr(main.tmdb_search, "get_movie_detail", lambda _: None)

    response = client.get("/api/movies/999999")
    assert response.status_code == 404


def test_filter_endpoint_returns_movies(monkeypatch) -> None:
    fake = {
        "movieId": 10, "title": "Action Flick", "genres": "Action", "description": "Boom",
        "poster_url": None, "release_date": "2020", "tmdb_rating": 7.2, "score": None,
    }
    monkeypatch.setattr(main.tmdb_search, "discover_movies", lambda params, page=1: [fake])

    response = client.post("/api/filter", json={"params": {"genre": "action"}, "page": 1})
    assert response.status_code == 200
    data = response.json()
    assert len(data["movies"]) == 1
    assert data["source"] == "tmdb:discover"


def test_filter_endpoint_empty_params(monkeypatch) -> None:
    monkeypatch.setattr(main.tmdb_search, "discover_movies", lambda params, page=1: [])

    response = client.post("/api/filter", json={"params": {}, "page": 1})
    assert response.status_code == 200
    assert response.json()["movies"] == []
