import os
import argparse
import sqlite3
import logging
from dotenv import load_dotenv


load_dotenv()


DEFAULT_DB_PATH = os.getenv("DB_PATH", "conan.db")


schema = """
CREATE TABLE IF NOT EXISTS package(
    package_id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS card_type(
    type_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rarity(
    rarity_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS color(
    color_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS category(
    category_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS card_base(
    card_base_id INTEGER PRIMARY KEY,
    card_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    type_id INTEGER NOT NULL,
    cost INTEGER CHECK (cost IS NULL OR cost BETWEEN 1 AND 9),
    ap INTEGER CHECK (
        ap IS NULL OR
        ap = 0 OR
        (ap BETWEEN 1000 AND 9000 AND ap % 1000 = 0)
    ),
    lp INTEGER CHECK (lp IS NULL OR lp IN (0, 1, 2, 3)),
    modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(type_id) REFERENCES card_type(type_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_card_base_card_id ON card_base(card_id);
CREATE INDEX IF NOT EXISTS idx_card_base_type_id ON card_base(type_id);

CREATE TABLE IF NOT EXISTS card(
    card_pk INTEGER PRIMARY KEY,
    card_num TEXT NOT NULL UNIQUE,
    card_base_id INTEGER NOT NULL,
    package_id INTEGER NOT NULL,
    rarity_id INTEGER NOT NULL,
    feature TEXT,
    drawing TEXT,
    illustrator TEXT,
    release_date DATE,
    image_url TEXT NOT NULL,
    image TEXT NOT NULL,
    modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(card_base_id) REFERENCES card_base(card_base_id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    FOREIGN KEY(package_id) REFERENCES package(package_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY(rarity_id) REFERENCES rarity(rarity_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_card_card_num ON card(card_num);
CREATE INDEX IF NOT EXISTS idx_card_base_id ON card(card_base_id);
CREATE INDEX IF NOT EXISTS idx_card_package_id ON card(package_id);
CREATE INDEX IF NOT EXISTS idx_card_rarity_id ON card(rarity_id);

CREATE TABLE IF NOT EXISTS card_base_color(
    card_base_id INTEGER NOT NULL,
    color_id INTEGER NOT NULL,
    modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY(card_base_id, color_id),

    FOREIGN KEY(card_base_id) REFERENCES card_base(card_base_id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    FOREIGN KEY(color_id) REFERENCES color(color_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_card_base_color_base ON card_base_color(card_base_id);
CREATE INDEX IF NOT EXISTS idx_card_base_color_color ON card_base_color(color_id);

CREATE TABLE IF NOT EXISTS card_base_category(
    card_base_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY(card_base_id, category_id),

    FOREIGN KEY(card_base_id) REFERENCES card_base(card_base_id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    FOREIGN KEY(category_id) REFERENCES category(category_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_card_base_category_base ON card_base_category(card_base_id);
CREATE INDEX IF NOT EXISTS idx_card_base_category_category ON card_base_category(category_id);

CREATE TABLE IF NOT EXISTS collection(
    card_pk INTEGER PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0 CHECK(count >= 0),
    watched INTEGER NOT NULL DEFAULT 0 CHECK(watched IN (0,1)),
    modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(card_pk) REFERENCES card(card_pk)
        ON DELETE CASCADE ON UPDATE RESTRICT
);

CREATE TRIGGER IF NOT EXISTS update_package_modified
AFTER UPDATE OF code, name ON package
FOR EACH ROW
BEGIN
    UPDATE package
    SET modified = CURRENT_TIMESTAMP
    WHERE package_id = NEW.package_id;
END;

CREATE TRIGGER IF NOT EXISTS update_card_type_modified
AFTER UPDATE OF name, sort_order ON card_type
FOR EACH ROW
BEGIN
    UPDATE card_type
    SET modified = CURRENT_TIMESTAMP
    WHERE type_id = NEW.type_id;
END;

CREATE TRIGGER IF NOT EXISTS update_rarity_modified
AFTER UPDATE OF name, sort_order ON rarity
FOR EACH ROW
BEGIN
    UPDATE rarity
    SET modified = CURRENT_TIMESTAMP
    WHERE rarity_id = NEW.rarity_id;
END;

CREATE TRIGGER IF NOT EXISTS update_color_modified
AFTER UPDATE OF name, sort_order ON color
FOR EACH ROW
BEGIN
    UPDATE color
    SET modified = CURRENT_TIMESTAMP
    WHERE color_id = NEW.color_id;
END;

CREATE TRIGGER IF NOT EXISTS update_category_modified
AFTER UPDATE OF name ON category
FOR EACH ROW
BEGIN
    UPDATE category
    SET modified = CURRENT_TIMESTAMP
    WHERE category_id = NEW.category_id;
END;

CREATE TRIGGER IF NOT EXISTS update_card_base_modified
AFTER UPDATE OF card_id, title, type_id, cost, ap, lp ON card_base
FOR EACH ROW
BEGIN
    UPDATE card_base
    SET modified = CURRENT_TIMESTAMP
    WHERE card_base_id = NEW.card_base_id;
END;

CREATE TRIGGER IF NOT EXISTS update_card_modified
AFTER UPDATE OF card_num, card_base_id, package_id, rarity_id, feature, drawing, illustrator, release_date, image_url, image ON card
FOR EACH ROW
BEGIN
    UPDATE card
    SET modified = CURRENT_TIMESTAMP
    WHERE card_pk = NEW.card_pk;
END;

CREATE TRIGGER IF NOT EXISTS update_collection_modified
AFTER UPDATE OF count, watched ON collection
FOR EACH ROW
BEGIN
    UPDATE collection
    SET modified = CURRENT_TIMESTAMP
    WHERE card_pk = NEW.card_pk;
END;

CREATE TRIGGER IF NOT EXISTS update_card_base_color_modified
AFTER UPDATE OF color_id ON card_base_color
FOR EACH ROW
BEGIN
    UPDATE card_base_color
    SET modified = CURRENT_TIMESTAMP
    WHERE card_base_id = NEW.card_base_id
      AND color_id = NEW.color_id;
END;

CREATE TRIGGER IF NOT EXISTS update_card_base_category_modified
AFTER UPDATE OF category_id ON card_base_category
FOR EACH ROW
BEGIN
    UPDATE card_base_category
    SET modified = CURRENT_TIMESTAMP
    WHERE card_base_id = NEW.card_base_id
      AND category_id = NEW.category_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_card_insert_collection
AFTER INSERT ON card
FOR EACH ROW
BEGIN
    INSERT INTO collection (card_pk, count, watched)
    VALUES (NEW.card_pk, 0, 0);
END;
"""

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create detective conan TCG database."
    )

    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    return parser


if __name__ == '__main__':
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        with sqlite3.connect(args.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()
            cursor.executescript(schema)
            conn.commit()
        logging.info("Database created successfully at %s", args.db_path)
    except Exception as e:
        logging.error("Database creation error: %s", e)