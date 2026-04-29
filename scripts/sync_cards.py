import os
import argparse
import requests
import json
import logging
import sqlite3
import sys
import time
import pickle
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
from PIL import Image
from dotenv import load_dotenv


load_dotenv()

DEFAULT_CARD_URL = "https://www.takaratomy.co.jp/products/conan-cardgame/cardlist/cards?page={}"
DEFAULT_CARD_IMAGE_URL = "https://www.takaratomy.co.jp/products/conan-cardgame/storage/card/{}"
DEFAULT_START_PAGE = 1
DEFAULT_DB_PATH = os.getenv("DB_PATH", "conan.db")
DEFAULT_TIMEOUT = 20
DEFAULT_SLEEP_SECONDS = 1.0
DEFAULT_PICKLE_NAME = "conan_cards.pkl"
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_IGNORE_FILE = "sync_cards.ignore.json"
DEFAULT_IMAGE_DOWNLOAD_DIR = "static/images"
DEFAULT_THUMBNAIL_DIR = "static/thumbnails"

TABLE_SORT_ORDER = {
    "package": 10,
    "card_type": 20,
    "rarity": 30,
    "color": 40,
    "category": 50,
    "card_base": 60,
    "card": 70,
}

PRIMARY_KEY_BY_TABLE = {
    "package": "code",
    "card_type": "name",
    "rarity": "name",
    "color": "name",
    "category": "name",
    "card_base": "card_id",
    "card": "card_num",
}


@dataclass
class FieldChange:
    field: str
    old: Any
    new: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RowChange:
    action: str          # insert | update
    table: str
    key: str
    changes: list[FieldChange] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "table": self.table,
            "key": self.key,
            "changes": [c.to_dict() for c in self.changes],
        }


@dataclass(frozen=True)
class IgnoreRule:
    table: str
    key_name: str
    key_value: str
    field: str

    def matches(self, table: str, key_name: str, key_value: str, field: str) -> bool:
        def match(rule_value: str, actual: str) -> bool:
            return rule_value == "*" or rule_value == actual

        return (
            match(self.table, table)
            and match(self.key_name, key_name)
            and match(self.key_value, key_value)
            and match(self.field, field)
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "table": self.table,
            "primary_key": self.key_name,
            "value": self.key_value,
            "field": self.field,
        }


class IgnoreRules:
    def __init__(self, rules: Iterable[IgnoreRule] = ()):
        self.rules = list(rules)
        self.log = True

    def should_skip(self, table: str, key_value: str, field: str) -> bool:
        key_name = PRIMARY_KEY_BY_TABLE.get(table, "id")
        for rule in self.rules:
            if rule.matches(table, key_name, key_value, field):
                return True
        return False

    def warn_skip(self, table: str, key_value: str, field: str, old: Any, new: Any) -> None:
        if not self.log:
            return
        
        key_name = PRIMARY_KEY_BY_TABLE.get(table, "id")
        logging.warning(
            "[SKIP] %s %s=%s | %s: %r -> %r",
            table,
            key_name,
            key_value,
            field,
            old,
            new,
        )

    def __bool__(self) -> bool:
        return bool(self.rules)

    @classmethod
    def from_path(cls, path: Optional[str]) -> "IgnoreRules":
        if not path:
            return cls()

        file_path = Path(path)
        if not file_path.exists():
            logging.info("Ignore file not found: %s (continuing without ignore rules)", file_path)
            return cls()

        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid ignore file JSON: {file_path}: {e}") from e

        if isinstance(payload, dict):
            if "rules" not in payload:
                raise ValueError("Ignore file object must contain a 'rules' array")
            payload = payload["rules"]

        if not isinstance(payload, list):
            raise ValueError("Ignore file must be a JSON array or an object with a 'rules' array")

        rules: list[IgnoreRule] = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Ignore rule #{index} must be an object")

            table = str(item.get("table", "")).strip()
            field = str(item.get("field", "")).strip() or str(item.get("column", "")).strip()
            if not table:
                raise ValueError(f"Ignore rule #{index} is missing 'table'")
            if not field:
                raise ValueError(f"Ignore rule #{index} is missing 'field'")

            primary_key = item.get("primary_key")
            key_name = item.get("key_name")
            key_value = item.get("key_value")
            value = item.get("value")

            resolved_key_name = PRIMARY_KEY_BY_TABLE.get(table, "id")
            resolved_key_value: Optional[str] = None

            if isinstance(primary_key, dict):
                pk_name = str(primary_key.get("name", "")).strip()
                pk_value = primary_key.get("value")
                if pk_name:
                    resolved_key_name = pk_name
                if pk_value is not None:
                    resolved_key_value = str(pk_value)
            elif primary_key is not None:
                resolved_key_value = str(primary_key)

            if key_name is not None:
                resolved_key_name = str(key_name).strip() or resolved_key_name

            for candidate in (key_value, value):
                if candidate is not None:
                    resolved_key_value = str(candidate)
                    break

            if resolved_key_value is None or resolved_key_value == "":
                raise ValueError(
                    f"Ignore rule #{index} must define primary key value using 'value', 'key_value', or primary_key.value"
                )

            rules.append(
                IgnoreRule(
                    table=table,
                    key_name=resolved_key_name,
                    key_value=resolved_key_value,
                    field=field,
                )
            )

        logging.info("Loaded %s ignore rule(s) from %s", len(rules), file_path)
        return cls(rules)


def write_ignore_template(path: str) -> None:
    output_path = Path(path)
    template = {
        "rules": [
            {
                "table": "card_base",
                "primary_key": {
                    "name": "card_id",
                    "value": "0584"
                },
                "field": "categories"
            },
            {
                "table": "card_base",
                "primary_key": {
                    "name": "card_id",
                    "value": "0723"
                },
                "field": "colors"
            },
            {
                "table": "card",
                "primary_key": {
                    "name": "card_num",
                    "value": "P067"
                },
                "field": "lp"
            }
        ]
    }
    output_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Wrote ignore template to %s", output_path.resolve())


class CardImporter:
    """
    Handles:
    - normalization
    - lookup upserts
    - card_base upsert
    - card upsert
    - relation replacement for colors/categories
    - preview via rollback
    - field-level ignore rules that also block DB writes

    Logging model:
    - inserts: one line per row, primary key only
    - updates: one line per row, changed fields grouped
    - skipped updates: warning line per skipped field
    - card_base_color + card_base_category are merged into card_base
    """

    def __init__(self, db_path: str, image_url: str, ignore_rules: Optional[IgnoreRules] = None):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

        self.image_url = image_url
        self.ignore_rules = ignore_rules or IgnoreRules()

        self.init_lookup_cache()

        self._ensure_indexes()

    def close(self) -> None:
        self.conn.close()

    def init_lookup_cache(self):
        self.lookup_cache: dict[str, dict[str, int]] = {
            "package": {},
            "card_type": {},
            "rarity": {},
            "color": {},
            "category": {},
        }

    def preview_cards(self, cards: Iterable[dict[str, Any]]) -> list[RowChange]:
        changes: list[RowChange] = []
        try:
            self.conn.execute("BEGIN")
            for raw_card in cards:
                changes.extend(self._import_one(raw_card))
            self.conn.rollback()
            self.init_lookup_cache()
            return self._normalize_change_list(changes)
        except Exception:
            self.conn.rollback()
            self.init_lookup_cache()
            raise

    def import_cards(self, cards: Iterable[dict[str, Any]]) -> list[RowChange]:
        changes: list[RowChange] = []
        try:
            self.conn.execute("BEGIN")
            for raw_card in cards:
                changes.extend(self._import_one(raw_card))
            self.conn.commit()
            return self._normalize_change_list(changes)
        except Exception:
            self.conn.rollback()
            raise

    def _import_one(self, raw_card: dict[str, Any]) -> list[RowChange]:
        card = self._normalize_card(raw_card)
        self._validate_card(card)

        changes: list[RowChange] = []

        package_id, package_change = self._get_or_create_package(card["package"])
        if package_change:
            changes.append(package_change)

        type_id, type_change = self._get_or_create_lookup("card_type", card["type"])
        if type_change:
            changes.append(type_change)

        rarity_id, rarity_change = self._get_or_create_lookup("rarity", card["rarity"])
        if rarity_change:
            changes.append(rarity_change)

        base_change, card_base_id = self._upsert_card_base(card, type_id)
        if base_change:
            changes.append(base_change)

        color_lookup_changes = self._ensure_colors_exist(card["colors"])
        changes.extend(color_lookup_changes)

        category_lookup_changes = self._ensure_categories_exist(card["categories"])
        changes.extend(category_lookup_changes)

        colors_field_change = self._replace_colors(card["card_id"], card_base_id, card["colors"])
        if colors_field_change:
            self._merge_field_change_into_card_base(changes, card["card_id"], colors_field_change)

        categories_field_change = self._replace_categories(card["card_id"], card_base_id, card["categories"])
        if categories_field_change:
            self._merge_field_change_into_card_base(changes, card["card_id"], categories_field_change)

        card_change = self._upsert_card(card, card_base_id, package_id, rarity_id)
        if card_change:
            changes.append(card_change)

        return changes

    # --------------------------------------------------------
    # Normalization
    # --------------------------------------------------------

    def _normalize_card(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "card_id": self._clean_text(raw.get("card_id")),
            "title": self._clean_text(raw.get("title")),
            "card_num": self._clean_text(raw.get("card_num")),
            "package": self._clean_text(raw.get("package")),
            "type": self._clean_text(raw.get("type")),
            "rarity": self._clean_text(raw.get("rarity")),
            "cost": self._to_int(raw.get("cost")),
            "ap": self._to_int(raw.get("ap")),
            "lp": self._to_int(raw.get("lp")),
            "feature": self._clean_text(raw.get("feature")),
            "drawing": self._clean_text(raw.get("drawing")),
            "illustrator": self._clean_text(raw.get("illustrator")),
            "release_date": self._normalize_date(raw.get("release_date")),
            "image_url": self._derive_image_url(raw, self.image_url),
            "image": self._derive_image_name(raw),
            "contain": self._clean_text(raw.get("contain")),
            "colors": self._normalize_colors(raw),
            "categories": self._normalize_categories(raw),
        }

    def _normalize_colors(self, raw: dict[str, Any]) -> list[str]:
        value = self._clean_text(raw.get("color"))
        return [c for c in value if c != ','] if value else []

    def _normalize_categories(self, raw: dict[str, Any]) -> list[str]:
        values = []
        for i in range(1, 4):
            category = self._clean_text(raw.get(f"category{i}"))
            if category:
                if ',' in category:
                    values.extend(category.split(','))
                else:
                    values.append(category)
        return sorted(set(v.strip() for v in values if v and v.strip()))

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    def _validate_card(self, card: dict[str, Any]) -> None:
        required_fields = ["card_id", "title", "card_num", "package", "type", "rarity"]
        for field_name in required_fields:
            if not card[field_name]:
                raise ValueError(f"Missing required field: {field_name}")

        cost = card["cost"]
        if cost is not None and not (1 <= cost <= 9):
            raise ValueError(f"Invalid cost for {card['card_num']}: {cost}")

        ap = card["ap"]
        if ap is not None:
            valid_ap = (ap == 0) or (1000 <= ap <= 9000 and ap % 1000 == 0)
            if not valid_ap:
                raise ValueError(f"Invalid ap for {card['card_num']}: {ap}")

        lp = card["lp"]
        if lp is not None and lp not in {0, 1, 2, 3}:
            raise ValueError(f"Invalid lp for {card['card_num']}: {lp}")

        if not card["image_url"]:
            logging.warning("Missing image_url for %s", card["card_num"])
        if not card["image"]:
            logging.warning("Missing image for %s", card["card_num"])

    # --------------------------------------------------------
    # Lookups
    # --------------------------------------------------------

    def _get_or_create_lookup(self, table: str, name: Optional[str]) -> tuple[int, Optional[RowChange]]:
        if not name:
            raise ValueError(f"{table} name is required")

        cached = self.lookup_cache[table].get(name)
        if cached is not None:
            return cached, None

        pk_map = {
            "card_type": "type_id",
            "rarity": "rarity_id",
            "color": "color_id",
            "category": "category_id",
        }
        pk = pk_map[table]

        existing = self.conn.execute(
            f"SELECT {pk} FROM {table} WHERE name = ?",
            (name,),
        ).fetchone()

        if existing is None:
            if table in {"card_type", "rarity", "color"}:
                self.conn.execute(
                    f"INSERT OR IGNORE INTO {table} (name, sort_order) VALUES (?, 0)",
                    (name,),
                )
            else:
                self.conn.execute(
                    f"INSERT OR IGNORE INTO {table} (name) VALUES (?)",
                    (name,),
                )

        row = self.conn.execute(
            f"SELECT {pk} FROM {table} WHERE name = ?",
            (name,),
        ).fetchone()
        row_id = int(row[0])
        self.lookup_cache[table][name] = row_id

        if existing is None:
            return row_id, RowChange(action="insert", table=table, key=name)

        return row_id, None

    def _get_or_create_package(self, package: str) -> tuple[int, Optional[RowChange]]:
        if not package:
            raise ValueError("package name is required")

        parse = package.split(' ', 1)
        if len(parse) == 2:
            code = parse[0]
            name = parse[1]
        else:
            code = "PR"
            name = parse[0]

        cached = self.lookup_cache["package"].get(code)
        if cached is not None:
            return cached, None

        existing = self.conn.execute(
            """
            SELECT package_id, code, name
            FROM package
            WHERE code = ?
            """,
            (code,),
        ).fetchone()

        if existing is None:
            self.conn.execute(
                "INSERT INTO package (code, name) VALUES (?, ?)",
                (code, name),
            )
            row = self.conn.execute(
                "SELECT package_id FROM package WHERE code = ?",
                (code,),
            ).fetchone()
            package_id = int(row["package_id"])
            self.lookup_cache["package"][code] = package_id
            return package_id, RowChange(action="insert", table="package", key=code)

        field_changes: list[FieldChange] = []
        final_name = existing["name"]

        if existing["name"] != name:
            if self.ignore_rules.should_skip("package", code, "name"):
                self.ignore_rules.warn_skip("package", code, "name", existing["name"], name)
            else:
                final_name = name
                field_changes.append(FieldChange(field="name", old=existing["name"], new=name))

        if field_changes:
            self.conn.execute(
                """
                UPDATE package
                SET name = ?
                WHERE code = ?
                """,
                (final_name, code),
            )

        package_id = int(existing["package_id"])
        self.lookup_cache["package"][code] = package_id

        if field_changes:
            return package_id, RowChange(
                action="update",
                table="package",
                key=code,
                changes=field_changes,
            )

        return package_id, None

    def _ensure_colors_exist(self, color_names: list[str]) -> list[RowChange]:
        changes: list[RowChange] = []
        for color_name in sorted(set(color_names)):
            _, change = self._get_or_create_lookup("color", color_name)
            if change:
                changes.append(change)
        return changes

    def _ensure_categories_exist(self, category_names: list[str]) -> list[RowChange]:
        changes: list[RowChange] = []
        for category_name in sorted(set(category_names)):
            _, change = self._get_or_create_lookup("category", category_name)
            if change:
                changes.append(change)
        return changes

    # --------------------------------------------------------
    # Card Base
    # --------------------------------------------------------

    def _upsert_card_base(self, card: dict[str, Any], type_id: int) -> tuple[Optional[RowChange], int]:
        existing = self.conn.execute(
            """
            SELECT
                card_base_id,
                card_id,
                title,
                type_id,
                cost,
                ap,
                lp
            FROM card_base
            WHERE card_id = ?
            """,
            (card["card_id"],),
        ).fetchone()

        if existing is None:
            self.conn.execute(
                """
                INSERT INTO card_base (
                    card_id, title, type_id, cost, ap, lp
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    card["card_id"],
                    card["title"],
                    type_id,
                    card["cost"],
                    card["ap"],
                    card["lp"],
                ),
            )
            row = self.conn.execute(
                "SELECT card_base_id FROM card_base WHERE card_id = ?",
                (card["card_id"],),
            ).fetchone()
            return RowChange(action="insert", table="card_base", key=card["card_id"]), int(row["card_base_id"])

        field_specs = [
            ("title", existing["title"], card["title"]),
            ("type_id", existing["type_id"], type_id),
            ("cost", existing["cost"], card["cost"]),
            ("ap", existing["ap"], card["ap"]),
            ("lp", existing["lp"], card["lp"]),
        ]

        field_changes: list[FieldChange] = []
        final_values = {
            "title": existing["title"],
            "type_id": existing["type_id"],
            "cost": existing["cost"],
            "ap": existing["ap"],
            "lp": existing["lp"],
        }

        for field_name, old_value, new_value in field_specs:
            if old_value == new_value:
                continue
            if self.ignore_rules.should_skip("card_base", card["card_id"], field_name):
                self.ignore_rules.warn_skip("card_base", card["card_id"], field_name, old_value, new_value)
                continue
            final_values[field_name] = new_value
            field_changes.append(FieldChange(field=field_name, old=old_value, new=new_value))

        if field_changes:
            self.conn.execute(
                """
                UPDATE card_base
                SET title = ?, type_id = ?, cost = ?, ap = ?, lp = ?
                WHERE card_id = ?
                """,
                (
                    final_values["title"],
                    final_values["type_id"],
                    final_values["cost"],
                    final_values["ap"],
                    final_values["lp"],
                    card["card_id"],
                ),
            )

        row_change = RowChange(
            action="update",
            table="card_base",
            key=card["card_id"],
            changes=field_changes,
        ) if field_changes else None

        return row_change, int(existing["card_base_id"])

    # --------------------------------------------------------
    # Card
    # --------------------------------------------------------

    def _upsert_card(
        self,
        card: dict[str, Any],
        card_base_id: int,
        package_id: int,
        rarity_id: int,
    ) -> Optional[RowChange]:
        existing = self.conn.execute(
            """
            SELECT
                card_num,
                card_base_id,
                package_id,
                rarity_id,
                feature,
                drawing,
                illustrator,
                release_date,
                image_url,
                image
            FROM card
            WHERE card_num = ?
            """,
            (card["card_num"],),
        ).fetchone()

        if existing is None:
            self.conn.execute(
                """
                INSERT INTO card (
                    card_num,
                    card_base_id,
                    package_id,
                    rarity_id,
                    feature,
                    drawing,
                    illustrator,
                    release_date,
                    image_url,
                    image
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card["card_num"],
                    card_base_id,
                    package_id,
                    rarity_id,
                    card["feature"],
                    card["drawing"],
                    card["illustrator"],
                    card["release_date"],
                    card["image_url"],
                    card["image"],
                ),
            )
            return RowChange(action="insert", table="card", key=card["card_num"])

        field_specs = [
            ("card_base_id", existing["card_base_id"], card_base_id),
            ("package_id", existing["package_id"], package_id),
            ("rarity_id", existing["rarity_id"], rarity_id),
            ("feature", existing["feature"], card["feature"]),
            ("drawing", existing["drawing"], card["drawing"]),
            ("illustrator", existing["illustrator"], card["illustrator"]),
            ("release_date", existing["release_date"], card["release_date"]),
            ("image_url", existing["image_url"], card["image_url"]),
            ("image", existing["image"], card["image"]),
        ]

        field_changes: list[FieldChange] = []
        final_values = {
            "card_base_id": existing["card_base_id"],
            "package_id": existing["package_id"],
            "rarity_id": existing["rarity_id"],
            "feature": existing["feature"],
            "drawing": existing["drawing"],
            "illustrator": existing["illustrator"],
            "release_date": existing["release_date"],
            "image_url": existing["image_url"],
            "image": existing["image"],
        }

        for field_name, old_value, new_value in field_specs:
            if old_value == new_value:
                continue
            if self.ignore_rules.should_skip("card", card["card_num"], field_name):
                self.ignore_rules.warn_skip("card", card["card_num"], field_name, old_value, new_value)
                continue
            final_values[field_name] = new_value
            field_changes.append(FieldChange(field=field_name, old=old_value, new=new_value))

        if field_changes:
            self.conn.execute(
                """
                UPDATE card
                SET card_base_id = ?,
                    package_id = ?,
                    rarity_id = ?,
                    feature = ?,
                    drawing = ?,
                    illustrator = ?,
                    release_date = ?,
                    image_url = ?,
                    image = ?
                WHERE card_num = ?
                """,
                (
                    final_values["card_base_id"],
                    final_values["package_id"],
                    final_values["rarity_id"],
                    final_values["feature"],
                    final_values["drawing"],
                    final_values["illustrator"],
                    final_values["release_date"],
                    final_values["image_url"],
                    final_values["image"],
                    card["card_num"],
                ),
            )

        return RowChange(
            action="update",
            table="card",
            key=card["card_num"],
            changes=field_changes,
        ) if field_changes else None

    # --------------------------------------------------------
    # Relations, collapsed into card_base
    # --------------------------------------------------------

    def _replace_colors(self, card_id: str, card_base_id: int, color_names: list[str]) -> Optional[FieldChange]:
        current_rows = self.conn.execute(
            """
            SELECT c.name
            FROM card_base_color cbc
            JOIN color c ON c.color_id = cbc.color_id
            WHERE cbc.card_base_id = ?
            ORDER BY c.name
            """,
            (card_base_id,),
        ).fetchall()

        old_set = {row["name"] for row in current_rows}
        new_set = set(color_names)

        if old_set == new_set:
            return None

        if self.ignore_rules.should_skip("card_base", card_id, "colors"):
            self.ignore_rules.warn_skip("card_base", card_id, "colors", sorted(old_set), sorted(new_set))
            return None

        self.conn.execute(
            "DELETE FROM card_base_color WHERE card_base_id = ?",
            (card_base_id,),
        )

        for color_name in sorted(new_set):
            color_id = self.lookup_cache["color"].get(color_name)
            if color_id is None:
                color_id, _ = self._get_or_create_lookup("color", color_name)
            self.conn.execute(
                """
                INSERT OR IGNORE INTO card_base_color (card_base_id, color_id)
                VALUES (?, ?)
                """,
                (card_base_id, color_id),
            )

        return FieldChange("colors", sorted(old_set), sorted(new_set))

    def _replace_categories(self, card_id: str, card_base_id: int, category_names: list[str]) -> Optional[FieldChange]:
        current_rows = self.conn.execute(
            """
            SELECT c.name
            FROM card_base_category cbc
            JOIN category c ON c.category_id = cbc.category_id
            WHERE cbc.card_base_id = ?
            ORDER BY c.name
            """,
            (card_base_id,),
        ).fetchall()

        old_set = {row["name"] for row in current_rows}
        new_set = set(category_names)

        if old_set == new_set:
            return None

        if self.ignore_rules.should_skip("card_base", card_id, "categories"):
            self.ignore_rules.warn_skip("card_base", card_id, "categories", sorted(old_set), sorted(new_set))
            return None

        self.conn.execute(
            "DELETE FROM card_base_category WHERE card_base_id = ?",
            (card_base_id,),
        )

        for category_name in sorted(new_set):
            category_id = self.lookup_cache["category"].get(category_name)
            if category_id is None:
                category_id, _ = self._get_or_create_lookup("category", category_name)
            self.conn.execute(
                """
                INSERT OR IGNORE INTO card_base_category (card_base_id, category_id)
                VALUES (?, ?)
                """,
                (card_base_id, category_id),
            )

        return FieldChange("categories", sorted(old_set), sorted(new_set))

    def _merge_field_change_into_card_base(
        self,
        changes: list[RowChange],
        card_id: str,
        field_change: FieldChange,
    ) -> None:
        for change in changes:
            if change.table == "card_base" and change.key == card_id:
                if change.action == "insert":
                    return
                change.changes.append(field_change)
                return

        changes.append(
            RowChange(
                action="update",
                table="card_base",
                key=card_id,
                changes=[field_change],
            )
        )

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------

    def _normalize_change_list(self, changes: list[RowChange]) -> list[RowChange]:
        """
        Deduplicate and merge row changes for the same table/key.
        card_base relation changes are already folded into card_base rows.
        """
        merged: dict[tuple[str, str], RowChange] = {}

        for change in changes:
            merge_key = (change.table, change.key)

            if merge_key not in merged:
                merged[merge_key] = RowChange(
                    action=change.action,
                    table=change.table,
                    key=change.key,
                    changes=list(change.changes),
                )
                continue

            existing = merged[merge_key]

            if existing.action == "insert":
                continue

            if change.action == "insert":
                existing.action = "insert"
                existing.changes = []
                continue

            field_map: dict[str, FieldChange] = {fc.field: fc for fc in existing.changes}
            for fc in change.changes:
                field_map[fc.field] = fc
            existing.changes = sorted(field_map.values(), key=lambda x: x.field)

        normalized = []
        for change in merged.values():
            if change.action == "update" and not change.changes:
                continue
            normalized.append(change)

        normalized.sort(key=self._sort_key_for_change)
        return normalized

    @staticmethod
    def _sort_key_for_change(change: RowChange) -> tuple[int, int, str]:
        table_rank = TABLE_SORT_ORDER.get(change.table, 999)
        action_rank = 0 if change.action == "insert" else 1
        return (table_rank, action_rank, change.key)

    def _ensure_indexes(self) -> None:
        self.conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_card_base_id ON card(card_base_id);
            CREATE INDEX IF NOT EXISTS idx_card_package_id ON card(package_id);
            CREATE INDEX IF NOT EXISTS idx_card_rarity_id ON card(rarity_id);
            CREATE INDEX IF NOT EXISTS idx_card_base_color_color ON card_base_color(color_id);
            CREATE INDEX IF NOT EXISTS idx_card_base_category_category ON card_base_category(category_id);
            """
        )

    @staticmethod
    def _clean_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        return value if value else None

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        return int(value)

    @staticmethod
    def _normalize_date(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    @staticmethod
    def _derive_image_name(raw: dict[str, Any]) -> str:
        return CardImporter._clean_text(raw.get("main_path")) or ""

    @staticmethod
    def _derive_image_url(raw: dict[str, Any], base_url: str) -> str:
        main_path = CardImporter._clean_text(raw.get("main_path"))
        if not main_path:
            return ""
        return base_url.format(main_path)

    @staticmethod
    def _derive_package_code(raw: dict[str, Any]) -> str:
        for key in ("package_code", "packageCode", "code"):
            value = CardImporter._clean_text(raw.get(key))
            if value:
                return value
        package_name = CardImporter._clean_text(raw.get("package"))
        return package_name or "UNKNOWN"


class CardScraper:
    def __init__(
        self,
        card_url_template: str,
        start_page: int = 1,
        sleep_seconds: float = 1.0,
        timeout: int = 20,
    ):
        self.card_url_template = card_url_template
        self.start_page = start_page
        self.sleep_seconds = sleep_seconds
        self.timeout = timeout
        self.session = requests.Session()

    def close(self) -> None:
        self.session.close()

    def scrape_all(self) -> list[dict[str, Any]]:
        all_cards: list[dict[str, Any]] = []
        page = self.start_page

        while True:
            url = self.card_url_template.format(page)
            logging.info("Scraping %s", url)

            data = self._fetch_page_json(url, page)
            cards = self._extract_cards(data, page)
            all_cards.extend(cards)

            last_page = data.get("lastPage")
            if last_page is None:
                raise RuntimeError("Last page number not found.")
            if not isinstance(last_page, int):
                raise RuntimeError(f"Last page is not an integer: {last_page}")

            logging.info("Fetched page %s with %s cards", page, len(cards))

            if page >= last_page:
                break

            page += 1
            time.sleep(self.sleep_seconds)

        logging.info("Scrape complete: %s cards total", len(all_cards))
        return all_cards

    def _fetch_page_json(self, url: str, page: int) -> dict[str, Any]:
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"Request failed for page {page}: {e}") from e

        try:
            data = response.json()
        except ValueError as e:
            raise RuntimeError(f"Invalid JSON on page {page}") from e

        if not isinstance(data, dict):
            raise RuntimeError(f"Top-level JSON is not an object on page {page}")

        return data

    @staticmethod
    def _extract_cards(data: dict[str, Any], page: int) -> list[dict[str, Any]]:
        cards = data.get("data")
        if cards is None:
            raise RuntimeError(f"Missing 'data' field on page {page}")
        if not isinstance(cards, list):
            raise RuntimeError(f"'data' is not a list on page {page}: {type(cards).__name__}")
        return cards


def export_changes_json(changes: list[RowChange], path: str) -> None:
    output_path = Path(path)
    payload = [c.to_dict() for c in changes]
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logging.info("Wrote changes to %s", output_path.resolve())


def prompt_yes_no(prompt: str, default_no: bool = True) -> bool:
    suffix = " [y/N]: " if default_no else " [Y/n]: "
    while True:
        answer = input(prompt + suffix).strip().lower()
        if not answer:
            return not default_no
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please enter y or n.")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else DEFAULT_LOG_LEVEL
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def summarize_changes(changes: list[RowChange]) -> Counter:
    return Counter(change.action for change in changes)


def print_change_summary(changes: list[RowChange], mode: str) -> None:
    if not changes:
        logging.info("[%s] No changes detected", mode)
        return

    counter = summarize_changes(changes)
    logging.info(
        "[%s] %s inserts, %s updates",
        mode,
        counter.get("insert", 0),
        counter.get("update", 0),
    )

    for change in changes:
        if change.action == "insert":
            logging.info("[INSERT] %s %s", change.table, change.key)
            continue

        fields = ", ".join(
            f"{fc.field}: {fc.old!r} -> {fc.new!r}"
            for fc in change.changes
        )
        logging.info("[UPDATE] %s %s | %s", change.table, change.key, fields)


def collect_cards_for_image_download(
    conn: sqlite3.Connection,
    changes: list[RowChange],
) -> list[tuple[str, str, str]]:
    card_nums: list[str] = []

    for change in changes:
        if change.table != "card":
            continue

        should_download = change.action == "insert" or any(
            fc.field in {"image_url", "image"} for fc in change.changes
        )
        if should_download:
            card_nums.append(change.key)

    if not card_nums:
        return []

    unique_card_nums = sorted(set(card_nums))
    placeholders = ", ".join("?" for _ in unique_card_nums)
    rows = conn.execute(
        f"""
        SELECT card_num, image_url, image
        FROM card
        WHERE card_num IN ({placeholders})
        ORDER BY card_num
        """,
        unique_card_nums,
    ).fetchall()

    return [
        (str(row["card_num"]), str(row["image_url"] or ""), str(row["image"] or ""))
        for row in rows
        if row["image_url"] and row["image"]
    ]


def download_card_images(
    cards: Iterable[tuple[str, str, str]],
    image_dir: str,
    thumbnail_dir: str,
    timeout: int,
    sleep_seconds: float,
) -> list[Exception]:
    output_dir = Path(image_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_thumbnail_dir = Path(thumbnail_dir)
    output_thumbnail_dir.mkdir(parents=True, exist_ok=True)

    logs: list[Exception] = []
    session = requests.Session()

    try:
        cards = list(cards)
        if not cards:
            logging.info("No card images need downloading.")
            return logs

        logging.info("Downloading %s card image(s) to %s", len(cards), output_dir.resolve())

        for card_num, image_url, image in cards:
            try:
                file_path = output_dir / image
                if os.path.exists(file_path):
                    logging.info("[DOWNLOAD-SKIP] %s | File already exists.", card_num)
                    continue

                response = session.get(image_url, timeout=timeout)
                response.raise_for_status()

                file_path.write_bytes(response.content)
                logging.info("[DOWNLOAD] %s -> %s", card_num, file_path)

                thumbnail_path =  output_thumbnail_dir / (image.rsplit(".", 1)[0] + ".webp")
                with Image.open(os.path.join(file_path)) as img:
                    if img.size[0] > img.size[1]:  # landscape
                        img = img.rotate(-90, expand=True)
                    img.thumbnail((220, 307), Image.LANCZOS)
                    img.save(thumbnail_path, "WEBP", quality=82)
                    logging.info("[CREATED-THUMBNAIL] %s -> %s", card_num, thumbnail_path)

                time.sleep(sleep_seconds)
            except Exception as e:
                logs.append(e)
                logging.warning("[DOWNLOAD-SKIP] %s | %s", card_num, e)
    finally:
        session.close()

    if logs:
        logging.warning("Image download completed with %s error(s)", len(logs))
    else:
        logging.info("Image download completed successfully")

    return logs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape detective conan cards, preview grouped SQLite changes, skip ignored field updates, and optionally commit them."
    )
    group = parser.add_mutually_exclusive_group()

    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_CARD_URL,
        help="Card API URL template with {} placeholder for page number",
    )
    parser.add_argument(
        "--image-url",
        default=DEFAULT_CARD_IMAGE_URL,
        help="Card image API URL template with {} placeholder for image filename",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=DEFAULT_START_PAGE,
        help=f"Start page (default: {DEFAULT_START_PAGE})",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help=f"Sleep seconds between pages (default: {DEFAULT_SLEEP_SECONDS})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Scrape once, preview changes, then prompt whether to commit.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-confirm commit after preview.",
    )
    parser.add_argument(
        "--export-json",
        default=None,
        help="Write accumulated grouped changes to this JSON file.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    parser.add_argument(
        "--ignore-file",
        default=DEFAULT_IGNORE_FILE,
        help=(
            "JSON file with field-level ignore rules. "
            f"If omitted, automatically looks for {DEFAULT_IGNORE_FILE} in the current directory."
        ),
    )
    parser.add_argument(
        "--write-ignore-template",
        action="store_true",
        help=(
            "Write an example ignore JSON file to --ignore-file and exit. "
            "The JSON format stores table, primary key name/value, and field."
        ),
    )
    parser.add_argument(
        "--image-download-dir",
        default=DEFAULT_IMAGE_DOWNLOAD_DIR,
        help=f"Directory to save images for newly added cards or cards with changed image_url/image (default: {DEFAULT_IMAGE_DOWNLOAD_DIR})",
    )
    parser.add_argument(
        "--thumbnail-dir",
        default=DEFAULT_THUMBNAIL_DIR,
        help=f"Directory to save thumbnails for newly added cards or cards with changed image_url/image (default: {DEFAULT_THUMBNAIL_DIR})",
    )
    parser.add_argument(
        "--skip-image-download",
        action="store_true",
        help="Do not download images after commit.",
    )
    group.add_argument(
        "--pickle-cards",
        action="store_true",
        help="Export scraped cards data.",
    )
    group.add_argument(
        "--unpickle-cards",
        action="store_true",
        help="Use existing cards data.",
    )
    parser.add_argument(
        "--pickle-name",
        default=DEFAULT_PICKLE_NAME,
        help=f"Pickle object name (default: {DEFAULT_PICKLE_NAME})",
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Only scrape cards data, do NOT modify the database.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.unpickle_cards and args.scrape_only:
        parser.error("Argument --scrape-only cannot be used with --unpickle-cards")

    configure_logging(args.verbose)

    if args.write_ignore_template:
        write_ignore_template(args.ignore_file)
        return 0

    ignore_rules = IgnoreRules.from_path(args.ignore_file)

    scraper = CardScraper(
        card_url_template=args.url,
        start_page=args.start_page,
        sleep_seconds=args.sleep,
        timeout=args.timeout,
    )
    importer = CardImporter(args.db_path, args.image_url, ignore_rules=ignore_rules)

    try:
        if args.unpickle_cards:
            with open(args.pickle_name, "rb") as file:
                cards = pickle.load(file)
        else:
            cards = scraper.scrape_all()

        if args.pickle_cards:
            with open(args.pickle_name, "wb") as file:
                pickle.dump(cards, file)

        if args.scrape_only:
            logging.info("Scrape card data only, early exit.")
            return 0

        if args.preview:
            logging.info("Starting preview")
            preview_changes = importer.preview_cards(cards)
            print_change_summary(preview_changes, mode="PREVIEW")

            if args.export_json:
                export_changes_json(preview_changes, args.export_json)

            if not preview_changes:
                logging.info("No changes detected. Nothing to commit.")
                return 0

            should_commit = True if args.yes else prompt_yes_no("Commit these changes?", default_no=True)
            if not should_commit:
                logging.info("Commit cancelled by user.")
                return 0
            
            # Disable skip logs
            importer.ignore_rules.log = False

            logging.info("Starting commit using the same scraped snapshot")
            committed_changes = importer.import_cards(cards)
            print_change_summary(committed_changes, mode="COMMIT")

            if args.export_json:
                export_changes_json(committed_changes, args.export_json)

            if not args.skip_image_download:
                cards_to_download = collect_cards_for_image_download(importer.conn, committed_changes)
                download_card_images(
                    cards=cards_to_download,
                    image_dir=args.image_download_dir,
                    thumbnail_dir= args.thumbnail_dir,
                    timeout=args.timeout,
                    sleep_seconds=args.sleep,
                )

            return 0

        logging.info("Starting commit without preview")
        committed_changes = importer.import_cards(cards)
        print_change_summary(committed_changes, mode="COMMIT")

        if args.export_json:
            export_changes_json(committed_changes, args.export_json)

        if not args.skip_image_download:
            cards_to_download = collect_cards_for_image_download(importer.conn, committed_changes)
            download_card_images(
                cards=cards_to_download,
                image_dir=args.image_download_dir,
                thumbnail_dir= args.thumbnail_dir,
                timeout=args.timeout,
                sleep_seconds=args.sleep,
            )

        return 0

    except KeyboardInterrupt:
        logging.error("Interrupted by user.")
        return 130
    except FileNotFoundError:
        logging.error("Card data file not found.")
        return 2
    except Exception as e:
        logging.exception("Sync failed: %s", e)
        return 1
    finally:
        importer.close()
        scraper.close()


if __name__ == "__main__":
    sys.exit(main())