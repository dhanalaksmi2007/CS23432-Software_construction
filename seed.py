"""Optional demo data. Run once:  python seed.py

DEMO ONLY: creates three demo accounts (admin, staff, student) that all use the
same demo password. Never use these accounts or this password on a real system.
Running the script again does nothing (it will not duplicate data).
"""
import os
import random
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

import database
from app import BASE_DIR

DB_PATH = os.environ.get("DATABASE", os.path.join(BASE_DIR, "instance", "canteen.db"))
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo@12345")
STUDENT_NAMES = ["Anitha", "Karthik", "Meena", "Rahul", "Divya", "Suresh", "Priya", "Arun"]


def seed(db_path, password=DEMO_PASSWORD):
    """Insert demo data. Returns True if data was added, False if already seeded."""
    database.init_db(db_path)
    conn = database.connect(db_path)
    try:
        if conn.execute("SELECT 1 FROM settings WHERE key = 'demo_seeded'").fetchone():
            return False
        hashed = generate_password_hash(password)
        for username, name, role in [
            ("admin", "Demo Admin", "admin"),
            ("staff", "Demo Canteen Staff", "staff"),
            ("student", "Demo Student", "student"),
        ]:
            conn.execute(
                "INSERT OR IGNORE INTO users (username, name, password_hash, role) VALUES (?, ?, ?, ?)",
                (username, name, hashed, role),
            )
        student_id = conn.execute("SELECT id FROM users WHERE username = 'student'").fetchone()["id"]
        staff_id = conn.execute("SELECT id FROM users WHERE username = 'staff'").fetchone()["id"]
        meals = [r["id"] for r in conn.execute("SELECT id FROM meals ORDER BY id")]

        rng = random.Random(42)  # fixed seed: the same demo data every time
        today = date.today()
        for offset in range(1, 15):  # past two weeks of tracking records
            day = today - timedelta(days=offset)
            for meal_id in meals[:3]:
                prepared = rng.randint(60, 120)
                served = max(0, prepared - rng.randint(3, 25))
                conn.execute(
                    "INSERT INTO food_tracking (meal_id, track_date, prepared_qty, served_qty, recorded_by) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (meal_id, day.isoformat(), prepared, served, staff_id),
                )
        for offset in (0, 1):  # preferences for today and tomorrow
            day = (today + timedelta(days=offset)).isoformat()
            for name in STUDENT_NAMES:
                conn.execute(
                    "INSERT INTO meal_preferences (user_id, student_name, meal_id, intended_date) VALUES (?, ?, ?, ?)",
                    (student_id if name == "Anitha" else None, name, rng.choice(meals[:3]), day),
                )
        deadline = (datetime.now() + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
        conn.execute(
            "INSERT INTO surplus_notices (item, quantity, location, deadline, created_by) VALUES (?, ?, ?, ?, ?)",
            ("Veg Thali", 15, "Canteen back counter", deadline.strftime("%Y-%m-%d %H:%M"), staff_id),
        )
        conn.execute("INSERT INTO settings (key, value) VALUES ('demo_seeded', '1')")
        conn.commit()
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    if seed(DB_PATH):
        print("Demo data added.")
        print("Demo logins (DEMO ONLY): admin / staff / student, password:", DEMO_PASSWORD)
    else:
        print("Demo data already exists. Nothing was changed.")
