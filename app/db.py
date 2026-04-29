import sqlite3
from flask import current_app, g


def get_db() -> sqlite3.Connection:
    """
    Return a per-request SQLite connection stored on Flask's g object.
    Opens a new connection if one doesn't exist for the current request.
    """
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DB_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None) -> None:
    """Close the request-scoped DB connection if it was opened."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def get_card_pk(conn: sqlite3.Connection, card_num: str) -> int:
    """Look up the primary key for a card by its card number."""
    row = conn.execute(
        "SELECT card_pk FROM card WHERE card_num = ?",
        (card_num,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Card not found: {card_num}")
    return row["card_pk"]
