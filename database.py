"""SQLite helpers: schema, connection handling and first-run setup."""
import os
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL CHECK (length(trim(name)) > 0),
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('student', 'staff', 'admin')),
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meals (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(name)) > 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS meal_preferences (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    student_name  TEXT NOT NULL CHECK (length(trim(student_name)) > 0),
    meal_id       INTEGER NOT NULL REFERENCES meals(id),
    intended_date TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pref_date_meal
    ON meal_preferences (intended_date, meal_id);

CREATE TABLE IF NOT EXISTS food_tracking (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_id      INTEGER NOT NULL REFERENCES meals(id),
    track_date   TEXT NOT NULL,
    prepared_qty INTEGER NOT NULL CHECK (prepared_qty >= 0),
    served_qty   INTEGER NOT NULL CHECK (served_qty >= 0),
    recorded_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (served_qty <= prepared_qty)
);
CREATE INDEX IF NOT EXISTS idx_tracking_date ON food_tracking (track_date);

CREATE TABLE IF NOT EXISTS surplus_notices (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item         TEXT NOT NULL CHECK (length(trim(item)) > 0),
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    location     TEXT NOT NULL CHECK (length(trim(location)) > 0),
    deadline     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'collected')),
    created_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    collected_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Starter menu, inserted only when the meals table is completely empty.
DEFAULT_MEALS = [
    "Veg Thali",
    "Chicken Biryani",
    "Masala Dosa",
    "Idli Sambar",
    "Chapati and Curry",
]


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path):
    """Create tables if missing. Safe to call on every start: existing rows are kept."""
    folder = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(folder, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('buffer_percent', '10')"
        )
        if conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO meals (name) VALUES (?)", [(m,) for m in DEFAULT_MEALS]
            )
        conn.commit()
    finally:
        conn.close()


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
