import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


def top_genres_from_sqlite(db_path: Path, limit: int = 10) -> tuple[list[str], list[list[object]], str]:
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT m.genres, r.rating
            FROM ratings r
            JOIN movies m ON m.movieId = r.movieId
            """,
            conn,
        )

    # Expand multi-genre rows (e.g., "Adventure|Animation|Children") into single genre rows.
    genres_split = df["genres"].fillna("(no genres)").astype(str).str.split("|")
    repeated_ratings = np.repeat(df["rating"].to_numpy(), genres_split.str.len().to_numpy())
    flat_genres = np.concatenate(genres_split.to_numpy())

    exploded = pd.DataFrame({"genre": flat_genres, "rating": repeated_ratings})
    exploded = exploded[exploded["genre"] != "(no genres listed)"]

    grouped = (
        exploded.groupby("genre", as_index=False)
        .agg(avg_rating=("rating", "mean"), rating_count=("rating", "count"))
        .sort_values(["rating_count", "avg_rating"], ascending=[False, False])
        .head(limit)
    )

    grouped["avg_rating"] = grouped["avg_rating"].round(2)

    columns = ["genre", "avg_rating", "rating_count"]
    rows = grouped[columns].values.tolist()
    insight = (
        f"Computed with pandas/numpy over local SQLite data. Returned top {len(rows)} genres "
        f"by rating volume, with average rating as secondary ranking."
    )
    return columns, rows, insight
