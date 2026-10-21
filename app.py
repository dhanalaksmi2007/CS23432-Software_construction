"""Smart Canteen Food Waste Reduction System - Flask application.

Run with:  python app.py
"""
import os
import re
import secrets
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import database
import services as svc

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
ROLES = ("student", "staff", "admin")
STAFF_ROLES = ("staff", "admin")


def _load_secret_key(instance_path):
    """Use the SECRET_KEY env var, else create and reuse a random key file."""
    from_env = os.environ.get("SECRET_KEY")
    if from_env:
        return from_env
    os.makedirs(instance_path, exist_ok=True)
    path = os.path.join(instance_path, "secret_key.txt")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(secrets.token_hex(32))
    with open(path, encoding="utf-8") as handle:
        return handle.read().strip()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    """Server-side role check. Hiding a menu link is never enough on its own."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def create_app(test_config=None):
    app = Flask(__name__, instance_path=os.path.join(BASE_DIR, "instance"))
    app.config.update(
        DATABASE=os.path.join(app.instance_path, "canteen.db"),
        CSRF_ENABLED=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _load_secret_key(app.instance_path)

    database.init_db(app.config["DATABASE"])
    app.teardown_appcontext(database.close_db)

    # ---------- request hooks ----------
    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.context_processor
    def inject_globals():
        return {"today": date.today().isoformat()}

    @app.before_request
    def load_user():
        g.user = None
        if request.endpoint == "static":
            return
        user_id = session.get("user_id")
        if user_id is not None:
            g.user = database.get_db().execute(
                "SELECT id, username, name, role FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if g.user is None:
                session.clear()

    @app.before_request
    def check_csrf():
        if request.method == "POST" and app.config["CSRF_ENABLED"]:
            sent = request.form.get("_csrf", "")
            expected = session.get("_csrf", "")
            if not expected or not secrets.compare_digest(sent, expected):
                abort(400, "Your form expired. Please go back, reload the page and try again.")

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    for code in (400, 403, 404):
        @app.errorhandler(code)
        def show_error(error):
            return render_template("error.html", error=error), error.code

    # ---------- helpers ----------
    def active_meals():
        return database.get_db().execute(
            "SELECT id, name FROM meals WHERE is_active = 1 ORDER BY name"
        ).fetchall()

    def valid_meal_id(raw):
        text = (raw or "").strip()
        if not text.isdigit():
            return None
        row = database.get_db().execute(
            "SELECT id FROM meals WHERE id = ? AND is_active = 1", (int(text),)
        ).fetchone()
        return row["id"] if row else None

    # ---------- authentication ----------
    @app.route("/")
    def index():
        return redirect(url_for("dashboard" if g.user else "login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            user = database.get_db().execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                return redirect(url_for("dashboard"))
            flash("Incorrect username or password.", "error")
            return render_template("login.html", username=username), 401
        return render_template("login.html", username="")

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        """Self-registration always creates a Student. Staff/Admin are made by an admin."""
        if g.user:
            return redirect(url_for("dashboard"))
        form, errors = request.form, {}
        if request.method == "POST":
            username = form.get("username", "").strip().lower()
            name, name_err = svc.clean_text(form.get("name"), "Full name")
            password = form.get("password", "")
            if name_err:
                errors["name"] = name_err
            if not re.fullmatch(r"[a-z0-9_]{3,30}", username):
                errors["username"] = "Username must be 3-30 letters, numbers or underscores."
            if len(password) < 8:
                errors["password"] = "Password must be at least 8 characters."
            elif password != form.get("confirm", ""):
                errors["confirm"] = "Passwords do not match."
            if not errors:
                try:
                    db = database.get_db()
                    db.execute(
                        "INSERT INTO users (username, name, password_hash, role) "
                        "VALUES (?, ?, ?, 'student')",
                        (username, name, generate_password_hash(password)),
                    )
                    db.commit()
                except sqlite3.IntegrityError:
                    errors["username"] = "That username is already taken."
            if not errors:
                flash("Account created. You can sign in now.", "success")
                return redirect(url_for("login"))
            return render_template("register.html", form=form, errors=errors), 400
        return render_template("register.html", form=form, errors=errors)

    # ---------- dashboard ----------
    @app.route("/dashboard")
    @login_required
    def dashboard():
        db = database.get_db()
        totals = svc.overall_totals(db)
        pref_total = db.execute("SELECT COUNT(*) FROM meal_preferences").fetchone()[0]
        pref_upcoming = db.execute(
            "SELECT COUNT(*) FROM meal_preferences WHERE intended_date >= ?",
            (date.today().isoformat(),),
        ).fetchone()[0]
        recent = list(reversed(svc.daily_summary(db, limit=7)))
        return render_template(
            "dashboard.html",
            totals=totals,
            pref_total=pref_total,
            pref_upcoming=pref_upcoming,
            notices=svc.active_notices(db),
            chart_rows=recent,
        )

    # ---------- meal preferences ----------
    def preferences_page(form=None, errors=None, status=200):
        db = database.get_db()
        sql = (
            "SELECT p.id, p.student_name, m.name AS meal_name, p.intended_date "
            "FROM meal_preferences p JOIN meals m ON m.id = p.meal_id"
        )
        if g.user["role"] == "student":
            rows = db.execute(
                sql + " WHERE p.user_id = ? ORDER BY p.intended_date DESC, p.id DESC LIMIT 100",
                (g.user["id"],),
            ).fetchall()
        else:
            rows = db.execute(
                sql + " ORDER BY p.intended_date DESC, p.id DESC LIMIT 100"
            ).fetchall()
        return render_template(
            "preferences.html",
            meals=active_meals(),
            preferences=rows,
            form=form or {"student_name": g.user["name"]},
            errors=errors or {},
        ), status

    @app.route("/preferences", methods=["GET", "POST"])
    @login_required
    def preferences():
        if request.method == "GET":
            return preferences_page()
        form, errors = request.form, {}
        name, err = svc.clean_text(form.get("student_name"), "Name")
        if err:
            errors["student_name"] = err
        meal_id = valid_meal_id(form.get("meal_id"))
        if meal_id is None:
            errors["meal_id"] = "Choose a meal from the list."
        when, err = svc.parse_date(form.get("intended_date"), "Intended date")
        if err:
            errors["intended_date"] = err
        elif when < date.today():
            errors["intended_date"] = "Intended date cannot be in the past."
        if errors:
            return preferences_page(form, errors, 400)
        db = database.get_db()
        db.execute(
            "INSERT INTO meal_preferences (user_id, student_name, meal_id, intended_date) "
            "VALUES (?, ?, ?, ?)",
            (g.user["id"], name, meal_id, when.isoformat()),
        )
        db.commit()
        flash("Your meal preference was saved.", "success")
        return redirect(url_for("preferences"))

    # ---------- demand estimation ----------
    @app.route("/demand")
    @roles_required(*STAFF_ROLES)
    def demand():
        db = database.get_db()
        chosen, err = svc.parse_date(request.args.get("date") or date.today().isoformat(), "Date")
        if err:
            flash(err, "error")
            chosen = date.today()
        buffer_pct = svc.get_buffer(db)
        rows = db.execute(
            "SELECT m.name, COUNT(p.id) AS demand FROM meal_preferences p "
            "JOIN meals m ON m.id = p.meal_id WHERE p.intended_date = ? "
            "GROUP BY m.id ORDER BY m.name",
            (chosen.isoformat(),),
        ).fetchall()
        estimates = [
            {"name": r["name"], "demand": r["demand"],
             "recommended": svc.recommended_quantity(r["demand"], buffer_pct)}
            for r in rows
        ]
        return render_template(
            "demand.html",
            chosen=chosen.isoformat(),
            buffer_pct=svc.format_decimal(buffer_pct),
            estimates=estimates,
            errors={},
        )

    @app.route("/demand/buffer", methods=["POST"])
    @roles_required(*STAFF_ROLES)
    def update_buffer():
        value, err = svc.parse_buffer(request.form.get("buffer_percent"))
        if err:
            flash(err, "error")
            return redirect(url_for("demand")), 302
        svc.set_buffer(database.get_db(), value)
        flash(f"Preparation buffer set to {svc.format_decimal(value)}%.", "success")
        return redirect(url_for("demand", date=request.form.get("date", "")))

    # ---------- food preparation and leftovers ----------
    def tracking_page(form=None, errors=None, status=200):
        rows = database.get_db().execute(
            "SELECT t.id, t.track_date, m.name AS meal_name, t.prepared_qty, t.served_qty, "
            "t.prepared_qty - t.served_qty AS leftover FROM food_tracking t "
            "JOIN meals m ON m.id = t.meal_id ORDER BY t.track_date DESC, t.id DESC LIMIT 100"
        ).fetchall()
        for_template = []
        for r in rows:
            item = dict(r)
            item["leftover_pct"] = svc.leftover_percent(r["prepared_qty"], r["leftover"])
            for_template.append(item)
        return render_template(
            "tracking.html", meals=active_meals(), records=for_template,
            form=form or {}, errors=errors or {},
        ), status

    @app.route("/tracking", methods=["GET", "POST"])
    @roles_required(*STAFF_ROLES)
    def tracking():
        if request.method == "GET":
            return tracking_page()
        form, errors = request.form, {}
        meal_id = valid_meal_id(form.get("meal_id"))
        if meal_id is None:
            errors["meal_id"] = "Choose a meal from the list."
        when, err = svc.parse_date(form.get("track_date"), "Date")
        if err:
            errors["track_date"] = err
        elif when > date.today():
            errors["track_date"] = "Date cannot be in the future."
        prepared, err = svc.parse_whole_number(form.get("prepared_qty"), "Prepared quantity")
        if err:
            errors["prepared_qty"] = err
        served, err = svc.parse_whole_number(form.get("served_qty"), "Served quantity")
        if err:
            errors["served_qty"] = err
        if not errors and served > prepared:
            errors["served_qty"] = "Served quantity cannot be greater than prepared quantity."
        if errors:
            return tracking_page(form, errors, 400)
        db = database.get_db()
        db.execute(
            "INSERT INTO food_tracking (meal_id, track_date, prepared_qty, served_qty, recorded_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (meal_id, when.isoformat(), prepared, served, g.user["id"]),
        )
        db.commit()
        flash(f"Saved. Leftover food: {svc.leftover_quantity(prepared, served)} portions.", "success")
        return redirect(url_for("tracking"))

    # ---------- surplus food ----------
    def surplus_page(form=None, errors=None, status=200):
        db = database.get_db()
        now = datetime.now().strftime(svc.DEADLINE_FORMAT)
        past = db.execute(
            "SELECT *, CASE WHEN status = 'collected' THEN 'Collected' "
            "WHEN deadline < ? THEN 'Expired' ELSE 'Active' END AS state "
            "FROM surplus_notices WHERE status = 'collected' OR deadline < ? "
            "ORDER BY created_at DESC, id DESC LIMIT 20",
            (now, now),
        ).fetchall()
        return render_template(
            "surplus.html", notices=svc.active_notices(db), past=past,
            form=form or {}, errors=errors or {},
        ), status

    @app.route("/surplus", methods=["GET", "POST"])
    @login_required
    def surplus():
        if request.method == "GET":
            return surplus_page()
        if g.user["role"] not in STAFF_ROLES:
            abort(403)
        form, errors = request.form, {}
        item, err = svc.clean_text(form.get("item"), "Food item", 100)
        if err:
            errors["item"] = err
        qty, err = svc.parse_whole_number(form.get("quantity"), "Quantity", minimum=1)
        if err:
            errors["quantity"] = err
        location, err = svc.clean_text(form.get("location"), "Collection location", 120)
        if err:
            errors["location"] = err
        deadline, err = svc.parse_deadline(form.get("deadline"))
        if err:
            errors["deadline"] = err
        elif deadline <= datetime.now():
            errors["deadline"] = "Collection deadline must be in the future."
        if errors:
            return surplus_page(form, errors, 400)
        db = database.get_db()
        db.execute(
            "INSERT INTO surplus_notices (item, quantity, location, deadline, created_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (item, qty, location, deadline.strftime(svc.DEADLINE_FORMAT), g.user["id"]),
        )
        db.commit()
        flash("Surplus notice published.", "success")
        return redirect(url_for("surplus"))

    @app.route("/surplus/<int:notice_id>/collect", methods=["POST"])
    @roles_required(*STAFF_ROLES)
    def collect_surplus(notice_id):
        db = database.get_db()
        notice = db.execute(
            "SELECT id, status FROM surplus_notices WHERE id = ?", (notice_id,)
        ).fetchone()
        if notice is None:
            abort(404)
        if notice["status"] == "collected":
            flash("That notice was already marked as collected.", "error")
        else:
            db.execute(
                "UPDATE surplus_notices SET status = 'collected', collected_at = ? WHERE id = ?",
                (datetime.now().strftime(svc.DEADLINE_FORMAT), notice_id),
            )
            db.commit()
            flash("Notice marked as collected.", "success")
        return redirect(url_for("surplus"))

    # ---------- reports ----------
    @app.route("/reports")
    @roles_required(*STAFF_ROLES)
    def reports():
        db = database.get_db()
        return render_template(
            "reports.html",
            totals=svc.overall_totals(db),
            daily=svc.daily_summary(db, 30),
            weekly=svc.weekly_summary(db, 12),
        )

    # ---------- meals (menu) ----------
    @app.route("/meals", methods=["GET", "POST"])
    @roles_required(*STAFF_ROLES)
    def meals():
        db = database.get_db()
        form, errors, status = request.form, {}, 200
        if request.method == "POST":
            name, err = svc.clean_text(form.get("name"), "Meal name", 80)
            if err:
                errors["name"] = err
            else:
                try:
                    db.execute("INSERT INTO meals (name) VALUES (?)", (name,))
                    db.commit()
                    flash(f"Added {name} to the menu.", "success")
                    return redirect(url_for("meals"))
                except sqlite3.IntegrityError:
                    errors["name"] = "That meal is already on the menu."
            status = 400
        rows = db.execute("SELECT id, name, is_active FROM meals ORDER BY name").fetchall()
        return render_template("meals.html", meals=rows, form=form, errors=errors), status

    @app.route("/meals/<int:meal_id>/toggle", methods=["POST"])
    @roles_required(*STAFF_ROLES)
    def toggle_meal(meal_id):
        db = database.get_db()
        if db.execute("SELECT 1 FROM meals WHERE id = ?", (meal_id,)).fetchone() is None:
            abort(404)
        db.execute("UPDATE meals SET is_active = 1 - is_active WHERE id = ?", (meal_id,))
        db.commit()
        return redirect(url_for("meals"))

    # ---------- admin: users and roles ----------
    @app.route("/admin/users")
    @roles_required("admin")
    def admin_users():
        users = database.get_db().execute(
            "SELECT id, username, name, role, created_at FROM users ORDER BY username"
        ).fetchall()
        return render_template("users.html", users=users, roles=ROLES)

    @app.route("/admin/users/<int:user_id>/role", methods=["POST"])
    @roles_required("admin")
    def change_role(user_id):
        role = request.form.get("role", "")
        if role not in ROLES:
            abort(400, "Unknown role.")
        if user_id == g.user["id"]:
            flash("You cannot change your own role.", "error")
            return redirect(url_for("admin_users"))
        db = database.get_db()
        if db.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
            abort(404)
        db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        db.commit()
        flash("Role updated.", "success")
        return redirect(url_for("admin_users"))

    return app


if __name__ == "__main__":
    # debug is off by default; set FLASK_DEBUG=1 while developing.
    create_app().run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
