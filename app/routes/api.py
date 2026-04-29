from flask import Blueprint, jsonify, request

from app.db import get_card_pk, get_db
from app.queries import upsert_quantity, upsert_watched

bp = Blueprint("api", __name__)


@bp.route("/update_card_quantity", methods=["POST"])
def update_card_quantity():
    try:
        data = request.get_json()
        card_num = data.get("card_num")
        quantity = int(data.get("quantity", 0))

        if quantity < 0:
            raise ValueError("Quantity cannot be negative")

        conn = get_db()
        card_pk = get_card_pk(conn, card_num)
        upsert_quantity(conn, card_pk, quantity)
        conn.commit()

        return jsonify({"success": True, "card_num": card_num, "quantity": quantity})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@bp.route("/toggle_watch", methods=["POST"])
def toggle_watch():
    try:
        data = request.get_json()
        card_num = data.get("card_num")
        watched = data.get("watched", False)

        conn = get_db()
        card_pk = get_card_pk(conn, card_num)
        upsert_watched(conn, card_pk, watched)
        conn.commit()

        return jsonify({"success": True, "card_num": card_num, "watched": watched})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400
