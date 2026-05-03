import os
import sqlite3

from flask import Blueprint, jsonify, render_template, request

from app.ai.pipeline import LOG_DB_PATH, agent_pipeline
from app.ai.providers import DEFAULT_MODEL, get_model_choices
from app.db import get_db

bp = Blueprint("ai", __name__, url_prefix="/ai")


@bp.route("/")
def ai_query_page():
    return render_template(
        "ai.html",
        models=get_model_choices(),
        default_model=DEFAULT_MODEL,
    )


@bp.route("/query", methods=["POST"])
def ai_query():
    data = request.get_json()
    user_query = (data.get("query") or "").strip()
    model = data.get("model", DEFAULT_MODEL)

    if not user_query:
        return jsonify({"success": False, "message": "Query cannot be empty."}), 400

    conn = get_db()
    result = agent_pipeline(conn, user_query, model)
    return jsonify(result)


@bp.route("/history")
def ai_history():
    try:
        with sqlite3.connect(LOG_DB_PATH) as log_conn:
            log_conn.row_factory = sqlite3.Row
            rows = log_conn.execute("""
                SELECT id, user_query, model, steps, success, error, created_at
                FROM ai_query_log
                ORDER BY created_at DESC
                LIMIT 50
            """).fetchall()
        return jsonify([dict(row) for row in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
