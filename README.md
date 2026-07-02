# Secret Hitler — Table Records

A self-hosted **Flask + htmx** tracker for your Secret Hitler game nights.
Leaderboard-first, art-deco styled, fully responsive. No page reloads —
htmx swaps the leaderboard, stats, and game log in place as you record games.

## Features
- **Leaderboard / stats dashboard** as the home screen (win rate, W–L, role mix)
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

## Roles & access
The tracker has two access levels:
- **Public (anyone)** — sees the leaderboard, stats, chronicle, and player pages, read-only.
- **Admin** — the only one who can see the **Record a Game** section, add players,
  and delete games. Sign in via the **Admin sign-in** link in the header.

Set credentials with environment variables (defaults shown — change them!):
```bash
export ADMIN_USER=admin
export ADMIN_PASSWORD=changeme
export SECRET_KEY=some-long-random-string   # signs the login session cookie
python app.py
```
Write endpoints are protected server-side too, so the admin-only sections
can't be reached just by knowing the URL.

## Run it
```bash
pip install -r requirements.txt
python app.py
```
Open <http://127.0.0.1:5000>.

The SQLite database `tracker.db` is created automatically on first
launch. Delete that file to reset everything.

## Deploy
It's a standard WSGI app (`app:app`). For anything beyond local play:
```bash
pip install gunicorn
gunicorn app:app
```
Point `TRACKER_DB` at a persistent path if your host has an ephemeral
filesystem, e.g. `TRACKER_DB=/data/tracker.db gunicorn app:app`.

## Project layout
```
app.py                    Flask app: routes, SQLite schema, stats, 
requirements.txt
static/css/style.css      Art-deco theme (red / black / cream)
templates/
  base.html               Shell: deco frame, header, htmx + font includes
  index.html              Dashboard (leaderboard + log form + game log)
  player.html             Single-player record page
  partials/               htmx fragments (swapped in without a reload)
    _leaderboard.html
    _games.html
    _game_form.html
    _roster_picker.html
    _summary.html
    _form_success.html
    _form_error.html
