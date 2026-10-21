"""Business rules: validation, demand estimation and report summaries."""
import re
from datetime import date, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation

DEFAULT_BUFFER = Decimal("10")
DEADLINE_FORMAT = "%Y-%m-%d %H:%M"


# ---------- calculations ----------
def recommended_quantity(expected_demand, buffer_percent):
    """expected demand x (1 + buffer / 100), rounded UP to a whole number.

    Decimal is used so that 10 x 1.10 is exactly 11 (floats would give 12).
    """
    demand = Decimal(str(expected_demand))
    buffer_pct = Decimal(str(buffer_percent))
    value = demand * (1 + buffer_pct / Decimal(100))
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def leftover_quantity(prepared, served):
    return prepared - served


def leftover_percent(prepared, leftover):
    if not prepared:
        return 0.0
    return round(leftover * 100 / prepared, 1)


def format_decimal(value):
    text = format(Decimal(value).normalize(), "f")
    return text


# ---------- validation (each returns (value, error_message)) ----------
def clean_text(raw, label, max_len=100):
    text = (raw or "").strip()
    if not text:
        return None, f"{label} is required."
    if len(text) > max_len:
        return None, f"{label} must be {max_len} characters or fewer."
    return text, None


def parse_whole_number(raw, label, minimum=0):
    text = (raw or "").strip()
    if not text:
        return None, f"{label} is required."
    if re.fullmatch(r"-\d+", text):
        return None, f"{label} cannot be negative."
    if not re.fullmatch(r"\d{1,7}", text):
        return None, f"{label} must be a whole number."
    value = int(text)
    if value < minimum:
        return None, f"{label} must be at least {minimum}."
    return value, None


def parse_buffer(raw):
    text = (raw or "").strip()
    if not text:
        return None, "Buffer percentage is required."
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None, "Buffer percentage must be a number."
    if not value.is_finite() or value < 0 or value > 100:
        return None, "Buffer percentage must be between 0 and 100."
    return value, None


def parse_date(raw, label):
    text = (raw or "").strip()
    if not text:
        return None, f"{label} is required."
    try:
        return date.fromisoformat(text), None
    except ValueError:
        return None, f"{label} must be a valid date."


def parse_deadline(raw):
    text = (raw or "").strip()
    if not text:
        return None, "Collection deadline is required."
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None, "Collection deadline must be a valid date and time."
    return value.replace(second=0, microsecond=0), None


# ---------- settings ----------
def get_buffer(db):
    row = db.execute("SELECT value FROM settings WHERE key = 'buffer_percent'").fetchone()
    try:
        return Decimal(row["value"]) if row else DEFAULT_BUFFER
    except InvalidOperation:
        return DEFAULT_BUFFER


def set_buffer(db, value):
    db.execute(
        "INSERT INTO settings (key, value) VALUES ('buffer_percent', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (format_decimal(value),),
    )
    db.commit()


# ---------- reports ----------
def _finish(rows, label_prefix=""):
    """Turn SQL rows into dicts and add leftover % and chart bar widths."""
    items = [
        {
            "label": f"{label_prefix}{r['period']}",
            "prepared": r["prepared"],
            "served": r["served"],
            "leftover": r["leftover"],
        }
        for r in rows
    ]
    biggest = max((i["prepared"] for i in items), default=0)
    for item in items:
        item["leftover_pct"] = leftover_percent(item["prepared"], item["leftover"])
        item["bar_width"] = round(item["prepared"] * 100 / biggest, 1) if biggest else 0
        item["served_share"] = (
            round(item["served"] * 100 / item["prepared"], 1) if item["prepared"] else 0
        )
    return items


_SUM_COLUMNS = (
    "SUM(prepared_qty) AS prepared, SUM(served_qty) AS served, "
    "SUM(prepared_qty - served_qty) AS leftover"
)


def daily_summary(db, limit=30):
    rows = db.execute(
        f"SELECT track_date AS period, {_SUM_COLUMNS} FROM food_tracking "
        "GROUP BY track_date ORDER BY track_date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return _finish(rows)


def weekly_summary(db, limit=12):
    # 'weekday 0' jumps to Sunday; '-6 days' then gives the Monday of that week.
    rows = db.execute(
        f"SELECT date(track_date, 'weekday 0', '-6 days') AS period, {_SUM_COLUMNS} "
        "FROM food_tracking GROUP BY period ORDER BY period DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return _finish(rows, "Week of ")


def overall_totals(db):
    row = db.execute(
        "SELECT COALESCE(SUM(prepared_qty), 0) AS prepared, "
        "COALESCE(SUM(served_qty), 0) AS served FROM food_tracking"
    ).fetchone()
    prepared, served = row["prepared"], row["served"]
    left = leftover_quantity(prepared, served)
    return {
        "prepared": prepared,
        "served": served,
        "leftover": left,
        "leftover_pct": leftover_percent(prepared, left),
    }


def active_notices(db, now=None):
    now = now or datetime.now()
    return db.execute(
        "SELECT * FROM surplus_notices WHERE status = 'active' AND deadline >= ? "
        "ORDER BY deadline",
        (now.strftime(DEADLINE_FORMAT),),
    ).fetchall()
