"""Create the SQLite database and tables. Safe to run more than once."""
import os

import database
from app import BASE_DIR

DB_PATH = os.environ.get("DATABASE", os.path.join(BASE_DIR, "instance", "canteen.db"))

if __name__ == "__main__":
    database.init_db(DB_PATH)
    print(f"Database ready: {DB_PATH}")
