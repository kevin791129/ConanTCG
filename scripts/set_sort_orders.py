import argparse
import logging
import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_PATH = os.getenv("DB_PATH", "conan.db")

SORT_ORDERS = {
    "card_type": [
        ('キャラ', 0),
        ('イベント', 1),
        ('事件', 2),
        ('パートナー', 3)
    ],
    "rarity": [
        ('D', 0),
        ('C', 1),
        ('CP', 2),
        ('CP2', 3),
        ('R', 4),
        ('RP', 5),
        ('SR', 6),
        ('SRP', 7),
        ('SRCP', 8),
        ('MR', 9),
        ('MRP', 10),
        ('MRCP', 11),
        ('SEC', 12),
        ('PR', 13)
    ],
    "color": [
        ('青', 0),
        ('緑', 1),
        ('白', 2),
        ('赤', 3),
        ('黄', 4),
        ('黒', 5)
    ],
}

def build_parser():
    parser = argparse.ArgumentParser(description="Set sort orders for filter options.")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    return parser

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
 
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
 
    try:
        with sqlite3.connect(args.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for table, entries in SORT_ORDERS.items():
                for name, order in entries:
                    conn.execute(
                        f"UPDATE {table} SET sort_order = ? WHERE name = ?",
                        (order, name),
                    )
            conn.commit()
        logging.info("Sort orders updated successfully at %s", args.db_path)
    except Exception as e:
        logging.error("Failed to update sort orders: %s", e)