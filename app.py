"""
Secret Hitler — Table Records
A Flask + htmx tracker for Secret Hitler game night results.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000

The SQLite database (tracker.db) is created on first run.
Delete tracker.db to start over.
"""

import os
import sqlite3
from functools import wraps
from datetime import date, timedelta

from flask import (
    Flask, g, request, render_template, make_response, abort, redirect,
    url_for, session, flash
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("TRACKER_DB", os.path.join(APP_DIR, "tracker.db"))

app = Flask(__name__)
# Change these in production, e.g. export SECRET_KEY=... ADMIN_PASSWORD=...
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

def is_admin():
    return bool(session.get("is_admin"))


@app.context_processor
def inject_admin():
    """Make is_admin available in every template."""
    return {"is_admin": is_admin()}


def admin_required(view):
    """Guard write endpoints server-side. htmx calls get a 403 fragment;
    normal navigations get redirected to the login page."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin():
            if request.headers.get("HX-Request"):
                resp = make_response(
                    render_template("partials/_form_error.html",
                                    message="Admin sign-in required to change records.",
                                    players=all_players(),
                                    win_conditions=WIN_CONDITIONS,
                                    today=date.today().isoformat()),
                    403,
                )
                return resp
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper

# --------------------------------------------------------------------------
# Domain rules
# --------------------------------------------------------------------------

# Each win condition maps to the faction that wins and a human label.
WIN_CONDITIONS = {
    "liberal_policies":  {"faction": "Liberal", "label": "Five Liberal policies enacted"},
    "hitler_executed":   {"faction": "Liberal", "label": "Hitler assassinated"},
    "fascist_policies":  {"faction": "Fascist", "label": "Six Fascist policies enacted"},
    "hitler_chancellor": {"faction": "Fascist", "label": "Hitler elected Chancellor"},
}

ROLES = ["Liberal", "Fascist", "Hitler"]

def role_faction(role):
    """Hitler counts as a Fascist for win purposes."""
    return "Liberal" if role == "Liberal" else "Fascist"


def fascist_count(n):
    """Standard Secret Hitler distribution of Fascists (excluding Hitler)."""
    if n <= 6:
        return 1
    if n <= 8:
        return 2
    return 3


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS games (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    played_on        TEXT NOT NULL,
    num_players      INTEGER NOT NULL,
    winning_faction  TEXT NOT NULL,
    win_condition    TEXT NOT NULL,
    liberal_policies INTEGER,
    fascist_policies INTEGER,
    notes            TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS game_players (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id    INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id  INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    won        INTEGER NOT NULL
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    db.commit()
    db.close()


def create_game(db, played_on, win_condition, roster_roles,
                liberal_policies=None, fascist_policies=None, notes=None, commit=True):
    """roster_roles: list of (player_id, role)."""
    winning = WIN_CONDITIONS[win_condition]["faction"]
    n = len(roster_roles)
    cur = db.execute(
        """INSERT INTO games (played_on, num_players, winning_faction, win_condition,
                              liberal_policies, fascist_policies, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (played_on, n, winning, win_condition, liberal_policies, fascist_policies, notes),
    )
    game_id = cur.lastrowid
    for pid, role in roster_roles:
        won = 1 if role_faction(role) == winning else 0
        db.execute(
            "INSERT INTO game_players (game_id, player_id, role, won) VALUES (?, ?, ?, ?)",
            (game_id, pid, role, won),
        )
    if commit:
        db.commit()
    return game_id


# --------------------------------------------------------------------------
# Query helpers
# --------------------------------------------------------------------------

def all_players():
    return get_db().execute("SELECT * FROM players ORDER BY name COLLATE NOCASE").fetchall()


def leaderboard_rows(min_games=1):
    db = get_db()
    rows = db.execute(
        """
        SELECT p.id, p.name,
               COUNT(gp.id)                          AS games,
               COALESCE(SUM(gp.won), 0)              AS wins,
               COALESCE(SUM(CASE WHEN gp.role='Liberal' THEN 1 ELSE 0 END), 0) AS lib_games,
               COALESCE(SUM(CASE WHEN gp.role='Fascist' THEN 1 ELSE 0 END), 0) AS fas_games,
               COALESCE(SUM(CASE WHEN gp.role='Hitler'  THEN 1 ELSE 0 END), 0) AS hitler_games
        FROM players p
        LEFT JOIN game_players gp ON gp.player_id = p.id
        GROUP BY p.id
        """
    ).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        d["losses"] = d["games"] - d["wins"]
        d["win_rate"] = (d["wins"] / d["games"]) if d["games"] else 0.0
        d["ranked"] = d["games"] >= min_games
        result.append(d)

    # Ranked players first (by wins, then win rate, then games, then name); unranked after.
    result.sort(key=lambda d: (
        not d["ranked"],
        -d["wins"],
        -d["win_rate"],
        -d["games"],
        d["name"].lower(),
    ))
    rank = 0
    prev_wins = None
    for i, d in enumerate(result):
        if d["ranked"]:
            if d["wins"] != prev_wins:
                rank = i + 1
                prev_wins = d["wins"]
            d["rank"] = rank
        else:
            d["rank"] = None
    return result


def game_detail_rows():
    """Recent games with their rosters attached."""
    db = get_db()
    games = db.execute("SELECT * FROM games ORDER BY played_on DESC, id DESC").fetchall()
    out = []
    for g_ in games:
        parts = db.execute(
            """SELECT gp.role, gp.won, p.name, p.id AS player_id
               FROM game_players gp JOIN players p ON p.id = gp.player_id
               WHERE gp.game_id = ?
               ORDER BY (gp.role='Hitler') DESC, (gp.role='Fascist') DESC, p.name""",
            (g_["id"],),
        ).fetchall()
        d = dict(g_)
        d["condition_label"] = WIN_CONDITIONS.get(g_["win_condition"], {}).get("label", g_["win_condition"])
        d["roster"] = [dict(p) for p in parts]
        out.append(d)
    return out


def summary_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) c FROM games").fetchone()["c"]
    lib = db.execute("SELECT COUNT(*) c FROM games WHERE winning_faction='Liberal'").fetchone()["c"]
    fas = total - lib
    return {
        "total_games": total,
        "liberal_wins": lib,
        "fascist_wins": fas,
        "liberal_pct": (lib / total * 100) if total else 0,
        "fascist_pct": (fas / total * 100) if total else 0,
        "total_players": db.execute("SELECT COUNT(*) c FROM players").fetchone()["c"],
    }


def player_detail(player_id):
    db = get_db()
    p = db.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
    if not p:
        return None
    rows = db.execute(
        """SELECT gp.*, g.played_on, g.winning_faction, g.win_condition, g.num_players
           FROM game_players gp JOIN games g ON g.id = gp.game_id
           WHERE gp.player_id = ?
           ORDER BY g.played_on DESC, g.id DESC""",
        (player_id,),
    ).fetchall()

    def bucket(role):
        gp = [r for r in rows if r["role"] == role]
        wins = sum(r["won"] for r in gp)
        return {"games": len(gp), "wins": wins,
                "rate": (wins / len(gp)) if gp else 0.0}

    games = len(rows)
    wins = sum(r["won"] for r in rows)
    history = []
    for r in rows:
        d = dict(r)
        d["condition_label"] = WIN_CONDITIONS.get(r["win_condition"], {}).get("label", r["win_condition"])
        history.append(d)
    return {
        "player": dict(p),
        "games": games,
        "wins": wins,
        "losses": games - wins,
        "win_rate": (wins / games) if games else 0.0,
        "by_role": {role: bucket(role) for role in ROLES},
        "history": history,
    }


# --------------------------------------------------------------------------
# htmx helper
# --------------------------------------------------------------------------

def trigger(resp, event):
    resp.headers["HX-Trigger"] = event
    return resp


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        board=leaderboard_rows(),
        games=game_detail_rows(),
        players=all_players(),
        summary=summary_stats(),
        win_conditions=WIN_CONDITIONS,
        today=date.today().isoformat(),
        fascist_count=fascist_count,
    )


@app.route("/leaderboard")
def leaderboard():
    return render_template("partials/_leaderboard.html", board=leaderboard_rows())


@app.route("/games/list")
def games_list():
    return render_template("partials/_games.html", games=game_detail_rows())


@app.route("/summary")
def summary():
    return render_template("partials/_summary.html", summary=summary_stats())


@app.route("/games/new")
@admin_required
def new_game_form():
    return render_template(
        "partials/_game_form.html",
        players=all_players(),
        win_conditions=WIN_CONDITIONS,
        today=date.today().isoformat(),
    )


@app.route("/games", methods=["POST"])
@admin_required
def create_game_route():
    f = request.form

    def form_error(message):
        return render_template(
            "partials/_form_error.html",
            message=message,
            players=all_players(),
            win_conditions=WIN_CONDITIONS,
            today=date.today().isoformat(),
        ), 422

    win_condition = f.get("win_condition", "")
    if win_condition not in WIN_CONDITIONS:
        return form_error("Choose a valid win condition.")

    included = f.getlist("include")  # list of player_id strings
    roster = []
    hitler_ct = 0
    for pid in included:
        role = f.get(f"role_{pid}", "Liberal")
        if role not in ROLES:
            role = "Liberal"
        if role == "Hitler":
            hitler_ct += 1
        roster.append((int(pid), role))

    n = len(roster)
    if n < 5 or n > 10:
        return form_error("Secret Hitler needs 5–10 players. You selected %d." % n)
    if hitler_ct != 1:
        return form_error("Exactly one player must be Hitler (you set %d)." % hitler_ct)

    played_on = f.get("played_on") or date.today().isoformat()

    def as_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    db = get_db()
    create_game(
        db, played_on, win_condition, roster,
        liberal_policies=as_int(f.get("liberal_policies")),
        fascist_policies=as_int(f.get("fascist_policies")),
        notes=(f.get("notes") or "").strip() or None,
    )

    resp = make_response(render_template(
        "partials/_form_success.html",
        faction=WIN_CONDITIONS[win_condition]["faction"],
    ))
    return trigger(resp, "gameLogged")


@app.route("/games/<int:game_id>", methods=["DELETE"])
@admin_required
def delete_game(game_id):
    db = get_db()
    db.execute("DELETE FROM games WHERE id=?", (game_id,))
    db.commit()
    resp = make_response("")
    return trigger(resp, "gameLogged")


@app.route("/players", methods=["POST"])
@admin_required
def add_player():
    name = (request.form.get("name") or "").strip()
    if name:
        db = get_db()
        try:
            db.execute("INSERT INTO players (name) VALUES (?)", (name,))
            db.commit()
        except sqlite3.IntegrityError:
            pass  # duplicate name; ignore
    resp = make_response(render_template(
        "partials/_roster_picker.html", players=all_players()))
    return trigger(resp, "playersChanged")


@app.route("/player/<int:player_id>")
def player_page(player_id):
    detail = player_detail(player_id)
    if not detail:
        abort(404)
    return render_template("player.html", d=detail)


# --------------------------------------------------------------------------
# Auth routes
# --------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = (request.form.get("username") or "").strip()
        pw = request.form.get("password") or ""
        if user == ADMIN_USER and pw == ADMIN_PASSWORD:
            session["is_admin"] = True
            nxt = request.args.get("next") or url_for("index")
            # Only allow local redirects
            if not nxt.startswith("/"):
                nxt = url_for("index")
            return redirect(nxt)
        error = "Incorrect username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


# --------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------

with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True)
