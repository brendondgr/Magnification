import sqlite3
import os
from pathlib import Path

# Get project root directory
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATABASE_PATH = PROJECT_ROOT / "data" / "magnificiation.db"

def migrate():
    print(f"Connecting to database at {DATABASE_PATH}...")
    if not DATABASE_PATH.exists():
        print("Database does not exist yet. No migration needed.")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # Check if the column already exists
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'site' not in columns:
            print("Adding 'site' column to 'jobs' table...")
            cursor.execute("ALTER TABLE jobs ADD COLUMN site VARCHAR(50)")
            conn.commit()
            print("Migration successful!")
        else:
            print("Column 'site' already exists.")
            
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
