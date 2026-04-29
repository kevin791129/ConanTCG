import sqlite3


# ---------------------------------------------------------------------------
# Shared filter queries (used on both collection and watchlist pages)
# ---------------------------------------------------------------------------

def fetch_filter_options(conn: sqlite3.Connection) -> dict:
    """
    Fetch all dropdown filter options shared across pages.
    Returns a dict with keys: packages, types, rarities, colors.
    """
    packages = conn.execute("""
        SELECT DISTINCT p.package_id, p.code, p.name
        FROM package p
        INNER JOIN card c ON p.package_id = c.package_id
        ORDER BY p.code
    """).fetchall()

    types = conn.execute("""
        SELECT DISTINCT ct.type_id, ct.name, ct.sort_order
        FROM card_type ct
        INNER JOIN card_base cb ON ct.type_id = cb.type_id
        INNER JOIN card c ON cb.card_base_id = c.card_base_id
        ORDER BY ct.sort_order, ct.name
    """).fetchall()

    rarities = conn.execute("""
        SELECT DISTINCT r.rarity_id, r.name, r.sort_order
        FROM rarity r
        INNER JOIN card c ON r.rarity_id = c.rarity_id
        ORDER BY r.sort_order, r.name
    """).fetchall()

    colors = conn.execute("""
        SELECT DISTINCT clr.color_id, clr.name, clr.sort_order
        FROM color clr
        INNER JOIN card_base_color cbc ON clr.color_id = cbc.color_id
        INNER JOIN card_base cb ON cbc.card_base_id = cb.card_base_id
        INNER JOIN card c ON cb.card_base_id = c.card_base_id
        ORDER BY clr.sort_order, clr.name
    """).fetchall()

    return dict(packages=packages, types=types, rarities=rarities, colors=colors)


# Reusable inline subquery that builds a concatenated color string per card_base
_COLOR_SUBQUERY = """
    LEFT JOIN (
        SELECT
            x.card_base_id,
            GROUP_CONCAT(x.name, '') AS color
        FROM (
            SELECT
                cbc.card_base_id,
                clr.name
            FROM card_base_color cbc
            JOIN color clr ON cbc.color_id = clr.color_id
            ORDER BY cbc.card_base_id, clr.sort_order, clr.name
        ) x
        GROUP BY x.card_base_id
    ) colors ON colors.card_base_id = cb.card_base_id
"""


# ---------------------------------------------------------------------------
# Collection page
# ---------------------------------------------------------------------------

VALID_SORT_COLUMNS = {
    "card_id": "cb.card_id, c.card_num",
    "card_num": "c.card_num",
}


def fetch_collection(conn: sqlite3.Connection, order_by: str) -> list[dict]:
    """Fetch all cards with collection quantity and watch status."""
    query = f"""
        SELECT
            c.card_pk,
            c.card_num,
            cb.card_id,
            cb.title,
            p.package_id,
            p.code AS package,
            p.name AS package_name,
            ct.type_id,
            ct.name AS type,
            r.name AS rarity,
            c.image,
            COALESCE(colors.color, '') AS color,
            COALESCE(col.count, 0) AS quantity,
            COALESCE(col.watched, 0) AS watched
        FROM card c
        JOIN card_base cb ON c.card_base_id = cb.card_base_id
        JOIN card_type ct ON cb.type_id = ct.type_id
        JOIN package p ON c.package_id = p.package_id
        JOIN rarity r ON c.rarity_id = r.rarity_id
        LEFT JOIN collection col ON c.card_pk = col.card_pk
        {_COLOR_SUBQUERY}
        ORDER BY {order_by}
    """
    return [dict(row) for row in conn.execute(query).fetchall()]


# ---------------------------------------------------------------------------
# Watchlist page
# ---------------------------------------------------------------------------

def fetch_watchlist(conn: sqlite3.Connection) -> list[dict]:
    """Fetch all cards marked as watched."""
    query = f"""
        SELECT
            c.card_pk,
            c.card_num,
            cb.card_id,
            cb.title,
            ct.type_id,
            ct.name AS type,
            r.name AS rarity,
            c.image,
            COALESCE(colors.color, '') AS color
        FROM card c
        JOIN card_base cb ON c.card_base_id = cb.card_base_id
        JOIN card_type ct ON cb.type_id = ct.type_id
        JOIN rarity r ON c.rarity_id = r.rarity_id
        INNER JOIN collection col ON c.card_pk = col.card_pk
        {_COLOR_SUBQUERY}
        WHERE col.watched = 1
        ORDER BY cb.card_id, c.card_num
    """
    return [dict(row) for row in conn.execute(query).fetchall()]


# ---------------------------------------------------------------------------
# Collection mutations
# ---------------------------------------------------------------------------

def upsert_quantity(conn: sqlite3.Connection, card_pk: int, quantity: int) -> None:
    """Insert or update a card's owned quantity in the collection."""
    exists = conn.execute(
        "SELECT 1 FROM collection WHERE card_pk = ?", (card_pk,)
    ).fetchone()

    if exists:
        conn.execute(
            "UPDATE collection SET count = ? WHERE card_pk = ?",
            (quantity, card_pk),
        )
    else:
        conn.execute(
            "INSERT INTO collection (card_pk, count, watched) VALUES (?, ?, 0)",
            (card_pk, quantity),
        )


def upsert_watched(conn: sqlite3.Connection, card_pk: int, watched: bool) -> None:
    """Insert or update a card's watched flag in the collection."""
    watched_int = 1 if watched else 0
    exists = conn.execute(
        "SELECT 1 FROM collection WHERE card_pk = ?", (card_pk,)
    ).fetchone()

    if exists:
        conn.execute(
            "UPDATE collection SET watched = ? WHERE card_pk = ?",
            (watched_int, card_pk),
        )
    else:
        conn.execute(
            "INSERT INTO collection (card_pk, count, watched) VALUES (?, 0, ?)",
            (card_pk, watched_int),
        )
