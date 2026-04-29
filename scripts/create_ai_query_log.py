import argparse
import logging
import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DEFAULT_LOG_DB_PATH = os.getenv("LOG_DB_PATH", "query_log.db")

schema = """
CREATE TABLE IF NOT EXISTS ai_query_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_query   TEXT NOT NULL,
    model        TEXT NOT NULL,
    steps        TEXT,
    success      INTEGER NOT NULL DEFAULT 0 CHECK(success IN (0, 1)),
    error        TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_query_log_created_at ON ai_query_log(created_at);
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize the AI query log database."
    )
    parser.add_argument(
        "--log-db-path",
        default=DEFAULT_LOG_DB_PATH,
        help=f"Path to log SQLite database (default: {DEFAULT_LOG_DB_PATH})",
    )
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        with sqlite3.connect(args.log_db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(schema)
            conn.commit()
        logging.info("AI query log database created successfully at %s", args.log_db_path)
    except Exception as e:
        logging.error("Failed to create AI query log database: %s", e)
