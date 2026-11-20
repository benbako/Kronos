"""Trade journal + profit/loss summary for the Kronos web UI.

Self-contained Flask blueprint: SQLite storage next to the webui folder,
no external services. Copy the `journal` folder into `webui/` and register
the blueprint in app.py:

    from journal import journal_bp
    app.register_blueprint(journal_bp)
"""

import os
import sqlite3
from contextlib import closing

from flask import Blueprint, redirect, render_template, request, url_for

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "journal.db")

journal_bp = Blueprint("journal", __name__, template_folder="templates", url_prefix="/journal")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'stocks',
    side TEXT NOT NULL DEFAULT 'long',
    status TEXT NOT NULL DEFAULT 'closed',
    quantity REAL NOT NULL DEFAULT 0,
    entry_price REAL,
    exit_price REAL,
    stop_price REAL,
    target_price REAL,
    pnl REAL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

MARKETS = [("stocks", "Stocks"), ("crypto", "Crypto"), ("forex", "Forex")]


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with closing(_connect()) as conn, conn:
        conn.executescript(_SCHEMA)


_init_db()


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value):
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"${abs(amount):,.2f}"


journal_bp.add_app_template_filter(_money, "money")


def _summarise(rows):
    closed = [r for r in rows if r["status"] == "closed"]
    pnls = [float(r["pnl"] or 0) for r in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net = sum(pnls)
    return {
        "closed_count": len(closed),
        "open_count": len(rows) - len(closed),
        "win_count": len(wins),
        "loss_count": len(losses),
        "net": net,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "win_rate": (len(wins) / len(closed) * 100) if closed else 0.0,
        "avg_win": gross_profit / len(wins) if wins else 0.0,
        "avg_loss": gross_loss / len(losses) if losses else 0.0,
        "expectancy": net / len(closed) if closed else 0.0,
    }


def _load():
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM journal_entries ORDER BY datetime(created_at) DESC, id DESC"
        ).fetchall()
    return rows, _summarise(rows)


def _render(rows, stats, error=None, status=200):
    return (
        render_template(
            "journal.html", trades=rows, s=stats, error=error, markets=MARKETS
        ),
        status,
    )


@journal_bp.get("/")
def index():
    rows, stats = _load()
    return _render(rows, stats)


@journal_bp.post("/add")
def add_entry():
    form = request.form
    symbol = (form.get("symbol") or "").strip().upper()
    quantity = _num(form.get("quantity"))
    entry = _num(form.get("entry_price"))

    if not symbol or not quantity or quantity <= 0 or not entry or entry <= 0:
        rows, stats = _load()
        return _render(
            rows,
            stats,
            error="Enter a symbol, a quantity and an entry price above zero.",
            status=400,
        )

    status = "closed" if form.get("status") == "closed" else "open"
    side = "short" if form.get("side") == "short" else "long"
    exit_price = _num(form.get("exit_price"))
    pnl = None
    if status == "closed" and exit_price and exit_price > 0:
        pnl = (exit_price - entry) * quantity * (-1 if side == "short" else 1)

    with closing(_connect()) as conn, conn:
        conn.execute(
            """INSERT INTO journal_entries
               (symbol, market, side, status, quantity, entry_price, exit_price,
                stop_price, target_price, pnl, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol,
                form.get("market") or "stocks",
                side,
                status,
                quantity,
                entry,
                exit_price if status == "closed" else None,
                _num(form.get("stop_price")),
                _num(form.get("target_price")),
                pnl,
                (form.get("notes") or "").strip() or None,
            ),
        )
    return redirect(url_for("journal.index"))


@journal_bp.post("/<int:entry_id>/close")
def close_entry(entry_id):
    exit_price = _num(request.form.get("exit_price"))
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT * FROM journal_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None or not exit_price or exit_price <= 0:
            return redirect(url_for("journal.index"))
        direction = -1 if row["side"] == "short" else 1
        pnl = (exit_price - (row["entry_price"] or 0)) * (row["quantity"] or 0) * direction
        conn.execute(
            "UPDATE journal_entries SET status = 'closed', exit_price = ?, pnl = ? WHERE id = ?",
            (exit_price, pnl, entry_id),
        )
    return redirect(url_for("journal.index"))


@journal_bp.post("/<int:entry_id>/delete")
def delete_entry(entry_id):
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
    return redirect(url_for("journal.index"))