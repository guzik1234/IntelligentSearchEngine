# IntelligentSearchEngine (Movie Insights Agent)

An AI-powered analytics search engine for movie-platform data.  
The system answers natural-language business questions and returns SQL, tables, charts, and short insights.

## Business Problem
Analysts and Product Managers need fast, reliable insights from movie-platform data without manually writing SQL.

## Project Goal
The user asks a question in natural language, and the system returns:
- generated SQL query
- result table
- chart/visualization
- short business insight

## Target Users
- Product Managers
- Data Analysts
- Business stakeholders

## MVP Scope
- NL -> SQL for analytical questions
- SQL safety validation (`SELECT` only)
- read-only database querying
- result visualization (table + chart)

## Example Questions
- Which genre had the highest watch time in Q4?
- How did churn change between Q3 and Q4?
- Which movies have the highest completion rate?
- What is the average rating by genre?
- Which user segment shows the best retention?

## Data Sources
- MovieLens dataset (movies, ratings)
- Optional enrichment: TMDB metadata
- Synthetic watch-history events for analytics KPIs

## Success Metrics
- SQL Accuracy: % of correct SQL queries
- Factual Accuracy: % of correct business answers
- Median Latency: end-to-end response time
- Safety Rate: % of unsafe queries blocked

## Tech Stack (planned)
- Python
- FastAPI
- PostgreSQL + SQLAlchemy
- Streamlit
- Local template SQL Agent
- pytest + GitHub Actions

## Out of Scope (for now)
- full video streaming platform
- payments/billing
- advanced account management

## Definition of Done (MVP)
- End-to-end flow works: question -> SQL -> result -> chart -> insight
- At least 10 business questions supported
- Safety validation is active (`SELECT` only)
- Basic metrics are reported in README
- Project runs locally with clear setup steps

## SQL Agent
- Backend uses a dedicated SQL Agent (`backend/sql_agent.py`) to convert user questions into SQL.
- SQL generation is local and template-based (no external LLM provider required).
- Only `SELECT` queries are allowed (safety guard).

## Local Raw Database
- Raw files are stored in `data/raw/ml-latest-small` (`movies.csv`, `ratings.csv`, `tags.csv`, `links.csv`).
- Backend auto-builds local SQLite DB on first run: `data/db/movielens.db`.
- `/api/search` now executes generated SQL directly on this local DB.

## Pandas / NumPy Analytics
- Backend includes `pandas` + `numpy` analytics module: `backend/analytics.py`.
- New endpoint: `GET /api/analytics/top-genres?limit=10`
- Response source: `sqlite+pandas+numpy`

## Run
- `python -m pip install -r requirements.txt`
- `python -m uvicorn backend.main:app --reload`
- Open `http://127.0.0.1:8000/`
