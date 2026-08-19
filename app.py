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
import itertools
from functools import wraps
from datetime import date, datetime

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
# Dashboard aggregates
# --------------------------------------------------------------------------

def _night_label(played_on):
    """'2026-07-03' -> ('Jul', '3'). Falls back to the raw string if unparseable.

    Month and day stay separate so the narrow layout can drop the month.
    """
    try:
        d = datetime.strptime(played_on, "%Y-%m-%d")
    except ValueError:
        return "", played_on
    return d.strftime("%b"), str(d.day)   # %-d is not portable to Windows


def game_shape_stats():
    """How games end, how table size skews them, and when they were played."""
    db = get_db()
    total = db.execute("SELECT COUNT(*) c FROM games").fetchone()["c"]

    counts = {r["win_condition"]: r["c"] for r in db.execute(
        "SELECT win_condition, COUNT(*) c FROM games GROUP BY win_condition"
    )}
    # Every condition gets a row, even at zero, so the chart keeps its shape.
    conditions = [
        {"key": key, "label": meta["label"], "faction": meta["faction"],
         "count": counts.get(key, 0),
         "pct": (counts.get(key, 0) / total * 100) if total else 0.0}
        for key, meta in WIN_CONDITIONS.items()
    ]
    conditions.sort(key=lambda c: (-c["count"], c["label"]))
    most = conditions[0]["count"] if conditions else 0

    by_size = []
    for r in db.execute(
        """SELECT num_players AS n, COUNT(*) AS games,
                  COALESCE(SUM(winning_faction='Liberal'), 0) AS lib
           FROM games GROUP BY num_players ORDER BY num_players"""
    ):
        d = dict(r)
        d["fas"] = d["games"] - d["lib"]
        d["lib_pct"] = d["lib"] / d["games"] * 100
        d["fas_pct"] = d["fas"] / d["games"] * 100
        by_size.append(d)

    nights = []
    for r in db.execute(
        """SELECT played_on, COUNT(*) AS games,
                  COALESCE(SUM(winning_faction='Liberal'), 0) AS lib
           FROM games GROUP BY played_on ORDER BY played_on"""
    ):
        d = dict(r)
        d["fas"] = d["games"] - d["lib"]
        d["month"], d["day"] = _night_label(d["played_on"])
        d["label"] = ("%s %s" % (d["month"], d["day"])).strip()
        nights.append(d)
    busiest = max((n["games"] for n in nights), default=0)
    # Only the first peak gets a printed cap — half the nights tie at the top and
    # a number over each one is noise.
    peak = next((i for i, n in enumerate(nights) if n["games"] == busiest), None)

    return {
        "conditions": conditions,
        "most": most,
        "by_size": by_size,
        "nights": nights,
        "busiest": busiest,
        "peak": peak,
        "total_games": total,
    }


def awards(min_games=5, min_role_games=3):
    """Superlatives for the hall of fame. Tiles with no qualifier are dropped."""
    db = get_db()
    rows = db.execute(
        """SELECT gp.player_id, gp.role, gp.won, p.name, g.played_on, g.id AS game_id
           FROM game_players gp
           JOIN games g   ON g.id = gp.game_id
           JOIN players p ON p.id = gp.player_id
           ORDER BY gp.player_id, g.played_on, g.id"""
    ).fetchall()

    stats = {}
    for r in rows:
        s = stats.setdefault(r["player_id"], {
            "id": r["player_id"], "name": r["name"], "games": 0,
            "lib_games": 0, "lib_wins": 0, "fas_games": 0, "fas_wins": 0,
            "hitler": 0, "results": [],
        })
        s["games"] += 1
        s["results"].append(r["won"])
        if r["role"] == "Hitler":
            s["hitler"] += 1
        if role_faction(r["role"]) == "Liberal":
            s["lib_games"] += 1
            s["lib_wins"] += r["won"]
        else:
            s["fas_games"] += 1
            s["fas_wins"] += r["won"]

    def longest_run(results, target):
        best = run = 0
        for won in results:
            run = run + 1 if won == target else 0
            best = max(best, run)
        return best

    for s in stats.values():
        s["streak"] = longest_run(s["results"], 1)
        s["drought"] = longest_run(s["results"], 0)

    def pick(candidates, value):
        """Highest value wins; ties break on games played, then name — as in leaderboard_rows."""
        if not candidates:
            return None
        return sorted(candidates, key=lambda s: (-value(s), -s["games"], s["name"].lower()))[0]

    everyone = list(stats.values())
    tiles = []

    def add(label, winner, value, detail):
        if winner:
            tiles.append({"label": label, "player_id": winner["id"], "name": winner["name"],
                          "value": value(winner), "detail": detail(winner)})

    libs = [s for s in everyone if s["lib_games"] >= min_role_games]
    add("Best Liberal", pick(libs, lambda s: s["lib_wins"] / s["lib_games"]),
        lambda s: "%.0f%%" % (s["lib_wins"] / s["lib_games"] * 100),
        lambda s: "%d of %d as Liberal" % (s["lib_wins"], s["lib_games"]))

    fas = [s for s in everyone if s["fas_games"] >= min_role_games]
    add("Best Fascist", pick(fas, lambda s: s["fas_wins"] / s["fas_games"]),
        lambda s: "%.0f%%" % (s["fas_wins"] / s["fas_games"] * 100),
        lambda s: "%d of %d on the right" % (s["fas_wins"], s["fas_games"]))

    seasoned = [s for s in everyone if s["games"] >= min_games]
    add("Longest Streak", pick([s for s in seasoned if s["streak"] > 1], lambda s: s["streak"]),
        lambda s: "%d" % s["streak"], lambda s: "wins in a row")
    add("Coldest Streak", pick([s for s in seasoned if s["drought"] > 1], lambda s: s["drought"]),
        lambda s: "%d" % s["drought"], lambda s: "losses in a row")

    add("Most Faithful", pick(everyone, lambda s: s["games"]),
        lambda s: "%d" % s["games"], lambda s: "games at the table")
    add("Marked by Fate", pick([s for s in everyone if s["hitler"] > 0], lambda s: s["hitler"]),
        lambda s: "%d" % s["hitler"], lambda s: "times dealt Hitler")

    return tiles


def pair_rows(min_together=4, limit=6):
    """Who wins together, and who keeps beating whom.

    Walked in Python rather than a self-join: ~950 pairings across the whole
    table, and this way the Liberal/Fascist split reuses role_faction().
    """
    db = get_db()
    rows = db.execute(
        """SELECT gp.game_id, gp.player_id, gp.role, gp.won, p.name
           FROM game_players gp JOIN players p ON p.id = gp.player_id"""
    ).fetchall()

    by_game = {}
    for r in rows:
        by_game.setdefault(r["game_id"], []).append(r)

    allies, rivals = {}, {}
    for roster in by_game.values():
        roster = sorted(roster, key=lambda r: r["name"].lower())
        for a, b in itertools.combinations(roster, 2):
            if role_faction(a["role"]) == role_faction(b["role"]):
                key = (a["player_id"], b["player_id"])
                d = allies.setdefault(key, {"id1": a["player_id"], "n1": a["name"],
                                            "id2": b["player_id"], "n2": b["name"],
                                            "games": 0, "wins": 0})
                d["games"] += 1
                d["wins"] += a["won"]          # same faction, so one outcome covers both
            else:
                key = (a["player_id"], b["player_id"])
                d = rivals.setdefault(key, {"id1": a["player_id"], "n1": a["name"],
                                            "id2": b["player_id"], "n2": b["name"],
                                            "games": 0, "w1": 0, "w2": 0})
                d["games"] += 1
                d["w1"] += a["won"]
                d["w2"] += b["won"]

    duos = [d for d in allies.values() if d["games"] >= min_together]
    for d in duos:
        d["losses"] = d["games"] - d["wins"]
        d["rate"] = d["wins"] / d["games"]
    duos.sort(key=lambda d: (-d["rate"], -d["games"], d["n1"].lower()))

    feuds = [d for d in rivals.values() if d["games"] >= min_together]
    for d in feuds:
        # Name the winner of the feud first so the row reads as a verdict.
        if d["w2"] > d["w1"]:
            d["id1"], d["n1"], d["w1"], d["id2"], d["n2"], d["w2"] = \
                d["id2"], d["n2"], d["w2"], d["id1"], d["n1"], d["w1"]
        d["edge"] = d["w1"] - d["w2"]
    feuds.sort(key=lambda d: (-d["edge"], -d["games"], d["n1"].lower()))

    return {"duos": duos[:limit], "rivals": feuds[:limit],
            "min_together": min_together}


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


@app.route("/dashboard")
def dashboard():
    # Server-rendered only: the gameLogged event comes from the admin form on the
    # home page, so there is nothing here for htmx to refresh.
    return render_template(
        "dashboard.html",
        summary=summary_stats(),
        shape=game_shape_stats(),
        awards=awards(),
        pairs=pair_rows(),
    )


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
