"""Single-admin sign-in, plus the guard that protects every write endpoint."""

import hmac
from functools import wraps

from flask import (
    Blueprint, current_app, make_response, redirect, render_template, request,
    session, url_for,
)

from .forms import game_form_context

bp = Blueprint("auth", __name__)


def is_admin():
    return bool(session.get("is_admin"))


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
                return make_response(
                    render_template("partials/_form_error.html",
                                    message="Admin sign-in required to change records.",
                                    **game_form_context()),
                    403,
                )
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def _safe_next(target):
    """Only allow same-site paths.

    A leading-slash check alone is not enough: '//evil.example' is a
    protocol-relative URL, and some browsers normalise a leading '/\' the
    same way.
    """
    # A slice, not target[1]: "/" on its own is a perfectly good destination.
    if target and target.startswith("/") and target[1:2] not in ("/", "\\"):
        return target
    return url_for("public.index")


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = (request.form.get("username") or "").strip()
        pw = request.form.get("password") or ""
        ok_user = hmac.compare_digest(user, current_app.config["ADMIN_USER"])
        ok_pw = hmac.compare_digest(pw, current_app.config["ADMIN_PASSWORD"])
        if ok_user and ok_pw:
            session["is_admin"] = True
            return redirect(_safe_next(request.args.get("next")))
        error = "Incorrect username or password."
    return render_template("login.html", error=error)


@bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("public.index"))
