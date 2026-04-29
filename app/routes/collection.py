from flask import Blueprint, render_template, request

from app.db import get_db
from app.queries import (
    VALID_SORT_COLUMNS,
    fetch_collection,
    fetch_filter_options,
    fetch_watchlist,
)

bp = Blueprint("collection", __name__)


@bp.route("/")
def display_cards():
    sort_by = request.args.get("sort", "card_id")
    order_by = VALID_SORT_COLUMNS.get(sort_by, VALID_SORT_COLUMNS["card_id"])

    conn = get_db()
    cards = fetch_collection(conn, order_by)
    filters = fetch_filter_options(conn)

    return render_template(
        "collection.html",
        cards=cards,
        current_sort=sort_by,
        **filters,
    )


@bp.route("/watchlist")
def display_watchlist():
    conn = get_db()
    cards = fetch_watchlist(conn)
    filters = fetch_filter_options(conn)

    return render_template("watchlist.html", cards=cards, **filters)
