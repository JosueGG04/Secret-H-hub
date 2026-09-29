# Secret Hitler — Table Records

A self-hosted **Flask + htmx** tracker for your Secret Hitler game nights.
Leaderboard-first, art-deco styled, fully responsive. No page reloads —
htmx swaps the leaderboard, stats, and game log in place as you record games.

## Features
- **Leaderboard** as the home screen (win rate, W–L, role mix), all-time or
  filtered to a single month
- **Dashboard** of table-wide trends: how games end, how table size skews the
  result, busiest nights, a hall of fame, and who wins together or keeps
  beating whom
- **Log a game** without leaving the page: date, roster with roles
  (Liberal / Fascist / Hitler), and win condition
- **Win conditions** map to the winning faction automatically:
  - *Five Liberal policies enacted* → Liberal
  - *Hitler assassinated* → Liberal
  - *Six Fascist policies enacted* → Fascist
  - *Hitler elected Chancellor* → Fascist
- **Per-player pages** with overall record and win rate broken down by role
- **Game log** with full roster, roles, and outcome; delete a game to correct it
- **Add players** on the fly
- **Paged for the long run** — the game log and each player's appearances page
  ten at a time, and the Game Nights chart shows one month per chip, so none of
  them sprawls as the archive grows

## Roles & access
The tracker has two access levels:
- **Public (anyone)** — sees the leaderboard, dashboard, chronicle, and player
  pages, read-only.
- **Admin** — the only one who can see the **Record a Game** section, add players,
  and delete games. Sign in via the **Admin sign-in** link in the header.

Write endpoints are protected server-side too, so the admin-only sections
can't be reached just by knowing the URL.

## Run it
```bash
pip install -r requirements.txt
cp .env.example .env          # then edit it — see Configuration
python -m flask --app wsgi run --debug
```
Open <http://127.0.0.1:5000>.

The SQLite database `instance/tracker.db` is created automatically on first
launch. Delete that file to reset everything.

## Configuration
Settings come from the environment. A `.env` file at the repo root is loaded on
startup, and real environment variables override it. Copy `.env.example` and
fill it in:

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `dev-only-change-me` | Signs the login session cookie |
| `ADMIN_USER` | `admin` | The single admin account |
| `ADMIN_PASSWORD` | `changeme` | Its password |
| `TRACKER_DB` | `instance/tracker.db` | Path to the SQLite file |

**Change `SECRET_KEY` and `ADMIN_PASSWORD` before exposing this to a network.**

## Deploy
It's a standard WSGI app (`wsgi:app`):
```bash
pip install -r requirements.txt
gunicorn wsgi:app
```
Point `TRACKER_DB` at a persistent path if your host has an ephemeral
filesystem, e.g. `TRACKER_DB=/data/tracker.db gunicorn wsgi:app`. The schema is
created on startup, but you can also do it explicitly:
```bash
python -m flask --app wsgi init-db
```

**gunicorn is Linux/macOS only** — it depends on `fcntl`, which Windows has no
equivalent for. On Windows, use the Flask dev server for game night, or
`pip install waitress && waitress-serve --port=8000 wsgi:app` if you want a
production server locally.

## Tests
```bash
pip install -r requirements-dev.txt
python -m pytest
```
Every test runs against a fresh temporary database, so your real records are
never touched.

## Project layout
```
wsgi.py                       WSGI entry point: app = create_app()
requirements.txt              runtime deps
requirements-dev.txt          + pytest
.env.example                  the settings above, ready to copy
instance/tracker.db           your records (gitignored)
secret_hitler/
  __init__.py                 create_app(): config, db, blueprints
  config.py                   Config / TestConfig, reads .env
  db.py                       per-request connection + init-db command
  schema.sql                  players, games, game_players
  domain.py                   win conditions, roles, faction rules
  repository.py               reads and writes against the three tables
  pagination.py               Page: offsets and the pager's own numbers
  forms.py                    shared context for the record-a-game form
  auth.py                     admin sign-in + the admin_required guard
  stats/
    leaderboard.py            standings, all-time or by month
    players.py                table totals, game log, one player's record
    dashboard.py              game shape, awards, pairings
  views/
    public.py                 read-only pages and htmx fragments
    admin.py                  record / delete a game, add a player
  static/
    css/style.css             art-deco theme (red / black / cream)
    css/fonts.css             self-hosted @font-face
    js/htmx.min.js            vendored
  templates/
    base.html                 shell: deco frame, header, nav
    index.html                home: leaderboard + log form + game log
    dashboard.html            trends, hall of fame, pairings
    player.html               single-player record page
    login.html                admin sign-in
    partials/                 htmx fragments (swapped in without a reload)
      _leaderboard.html  _games.html  _player_games.html
      _nights.html  _game_form.html  _roster_picker.html
      _summary.html  _form_success.html  _form_error.html
      _macros.html            the numbered pager, shared by both game lists
tests/                        pytest suite on a temporary database
```
