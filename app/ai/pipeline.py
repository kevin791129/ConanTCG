import logging
import os
import sqlite3

from dotenv import load_dotenv

from app.ai.prompt import SYSTEM_PROMPT
from app.ai.providers import DEFAULT_MODEL, get_provider

load_dotenv()

FORBIDDEN_KEYWORDS = {"drop", "delete", "insert", "update", "alter", "create"}
LOG_DB_PATH = os.getenv("LOG_DB_PATH", "query_log.db")
MAX_STEPS = 5
MAX_RESULT_ROWS = 50  # cap rows fed back to LLM to avoid blowing context


def is_safe_sql(sql: str) -> bool:
    """Reject any SQL that is not a plain SELECT or contains write keywords."""
    first_word = sql.strip().lower().split()[0]
    if first_word != "select":
        return False
    return not any(kw in sql.lower() for kw in FORBIDDEN_KEYWORDS)


def run_sql(conn: sqlite3.Connection, sql: str) -> list[dict]:
    """Execute a SELECT query and return rows as dicts.
    Works regardless of whether conn.row_factory is set.
    """
    cursor = conn.execute(sql)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def parse_response(text: str) -> tuple[str, str]:
    """
    Parse the LLM response into (type, content).
    type is 'query', 'answer', or 'invalid'.
    """
    text = text.strip()
    if text.upper().startswith("QUERY:"):
        return "query", text[len("QUERY:"):].strip()
    if text.upper().startswith("ANSWER:"):
        return "answer", text[len("ANSWER:"):].strip()
    return "invalid", text


def log_query(
    user_query: str,
    model: str,
    steps: list[dict],
    success: bool,
    error: str | None = None,
) -> None:
    """Persist query session to the separate logs database."""
    import json
    try:
        with sqlite3.connect(LOG_DB_PATH) as log_conn:
            log_conn.execute(
                """
                INSERT INTO ai_query_log (user_query, model, steps, success, error)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_query, model, json.dumps(steps), 1 if success else 0, error),
            )
            log_conn.commit()
    except Exception as e:
        logging.warning("Failed to log AI query: %s", e)


def agent_pipeline(
    conn: sqlite3.Connection,
    user_query: str,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Run the agentic Text-to-SQL pipeline.

    The LLM iterates between QUERY and ANSWER steps until it either
    produces a final ANSWER or hits MAX_STEPS.

    Returns a dict with keys:
        success  (bool)
        answer   (str | None)   — final natural language answer
        steps    (list)         — each query step with sql and results
        message  (str | None)   — error message for the UI
    """
    provider = get_provider(model)
    messages = [{"role": "user", "content": user_query}]
    steps = []

    try:
        for step_num in range(MAX_STEPS):
            raw = provider.chat(SYSTEM_PROMPT, messages)
            kind, content = parse_response(raw)

            if kind == "answer":
                log_query(user_query, model, steps, True)
                return {
                    "success": True,
                    "answer": content,
                    "steps": steps,
                    "message": None,
                }

            if kind == "query":
                sql = content

                if not is_safe_sql(sql):
                    log_query(user_query, model, steps, False, "UNSAFE SQL")
                    return {
                        "success": False,
                        "answer": None,
                        "steps": steps,
                        "message": "Generated query was rejected for safety reasons.",
                    }

                try:
                    results = run_sql(conn, sql)
                    truncated = results[:MAX_RESULT_ROWS]
                    step = {"sql": sql, "results": truncated, "row_count": len(results)}
                    steps.append(step)

                    # Feed results back so the LLM can reason about them
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Query returned {len(results)} row(s):\n{truncated}\n"
                            f"{'(truncated to first 50 rows)' if len(results) > MAX_RESULT_ROWS else ''}"
                            "\nContinue — run another QUERY if needed, or give your ANSWER."
                        ),
                    })

                except sqlite3.Error as e:
                    # Feed the error back for self-correction
                    logging.warning("SQL error on step %d: %s", step_num + 1, e)
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({
                        "role": "user",
                        "content": f"That query failed with error: {e}\nPlease correct it and try again.",
                    })

            else:
                # LLM returned something unparseable — try to recover once
                logging.warning("Unparseable LLM response: %s", content)
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "Please respond with either QUERY: <sql> or ANSWER: <text>.",
                })

        # Hit MAX_STEPS without an ANSWER
        log_query(user_query, model, steps, False, "MAX_STEPS exceeded")
        return {
            "success": False,
            "answer": None,
            "steps": steps,
            "message": f"Could not complete in {MAX_STEPS} steps. Try a simpler question.",
        }

    except Exception as e:
        logging.error("Agent pipeline error: %s", e)
        log_query(user_query, model, steps, False, str(e))
        return {
            "success": False,
            "answer": None,
            "steps": steps,
            "message": "Something went wrong. Please try again.",
        }
