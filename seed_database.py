"""
CardioMate Database Setup and Seeder
-----------------------------------
Initializes and populates cardiomate_history.db with sample users, logins,
passwords, and database schemas required by CardioMate AI engine.
"""

import sqlite3
from datetime import datetime
import os
import sys

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cardiomate_history.db")


def get_connection(db_path: str = DB_FILE) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_database(conn: sqlite3.Connection) -> None:
    """Ensures all necessary tables exist in the database."""
    cursor = conn.cursor()

    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT NOT NULL,
        university TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    # 2. Cardiac Analysis Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cardiac_analysis_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        risk_score REAL NOT NULL,
        status TEXT NOT NULL,
        signal_variance REAL NOT NULL,
        active_drugs TEXT NOT NULL,
        comorbidities TEXT NOT NULL,
        selected_lead TEXT NOT NULL DEFAULT 'II',
        ai_recommendation TEXT NOT NULL,
        ai_source TEXT NOT NULL
    );
    """)

    # Check if 'selected_lead' column exists in existing cardiac_analysis_logs table
    cursor.execute("PRAGMA table_info(cardiac_analysis_logs);")
    existing_cols = [row["name"] for row in cursor.fetchall()]
    if "selected_lead" not in existing_cols:
        cursor.execute("ALTER TABLE cardiac_analysis_logs ADD COLUMN selected_lead TEXT NOT NULL DEFAULT 'II';")
        print("-> Added missing 'selected_lead' column to cardiac_analysis_logs table.")

    # 3. Intraoperative Telemetry Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS intraop_telemetry_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        imminent_risk_score REAL NOT NULL,
        decompensation_trend REAL NOT NULL,
        status TEXT NOT NULL,
        signal_variance REAL NOT NULL,
        map_mmHg REAL NOT NULL,
        ai_recommendation TEXT NOT NULL,
        ai_source TEXT NOT NULL
    );
    """)

    conn.commit()


def seed_sample_users(conn: sqlite3.Connection) -> int:
    """Populates users table with initial doctor, student, and clinician accounts."""
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Sample user records
    sample_users = [
        # Preserving and ensuring existing user
        {
            "username": "crushbek2008",
            "password": "12265105",
            "full_name": "YORKINOV SHOKHJAHON",
            "university": "Tashkent Medical Academy",
            "created_at": "2026-10-16 00:20:04",
        },
        # Senior Clinical Cardiologist
        {
            "username": "dr_jasur",
            "password": "cardioPass#2026",
            "full_name": "Dr. Jasur Alimov",
            "university": "Tashkent Medical Academy",
            "created_at": now_str,
        },
        # Pediatric Cardiologist
        {
            "username": "dr_malika",
            "password": "pediatricHeart!99",
            "full_name": "Dr. Malika Karimova",
            "university": "Samarkand State Medical University",
            "created_at": now_str,
        },
        # Cardiothoracic Surgeon
        {
            "username": "dr_azamat",
            "password": "surgeonSecure#7",
            "full_name": "Dr. Azamat Tursunov",
            "university": "Republican Specialized Surgery Center",
            "created_at": now_str,
        },
        # Electrophysiology Specialist
        {
            "username": "dr_elena",
            "password": "ecgAnalysis@2026",
            "full_name": "Dr. Elena Petrova",
            "university": "Akfa University School of Medicine",
            "created_at": now_str,
        },
        # Cardiology Resident
        {
            "username": "student_bobur",
            "password": "resident2026!",
            "full_name": "Bobur Umarov",
            "university": "Tashkent Pediatric Medical Institute",
            "created_at": now_str,
        },
        # Medical Student
        {
            "username": "student_nilufar",
            "password": "medStudent@42",
            "full_name": "Nilufar Rakhimova",
            "university": "Tashkent Medical Academy",
            "created_at": now_str,
        },
        # System Administrator
        {
            "username": "admin",
            "password": "AdminCardio2026!",
            "full_name": "CardioMate Administrator",
            "university": "CardioMate Clinical AI Labs",
            "created_at": now_str,
        },
    ]

    inserted_count = 0
    for user in sample_users:
        cursor.execute("SELECT id FROM users WHERE username = ?", (user["username"],))
        exists = cursor.fetchone()
        if not exists:
            cursor.execute(
                """
                INSERT INTO users (username, password, full_name, university, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user["username"], user["password"], user["full_name"], user["university"], user["created_at"]),
            )
            inserted_count += 1

    conn.commit()
    return inserted_count


def list_users(conn: sqlite3.Connection) -> None:
    """Prints all users currently registered in the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password, full_name, university, created_at FROM users ORDER BY id ASC")
    rows = cursor.fetchall()

    print("\n" + "=" * 95)
    print(f"{'ID':<4} | {'USERNAME':<16} | {'PASSWORD':<18} | {'FULL NAME':<26} | {'UNIVERSITY'}")
    print("-" * 95)
    for row in rows:
        print(f"{row['id']:<4} | {row['username']:<16} | {row['password']:<18} | {row['full_name']:<26} | {row['university']}")
    print("=" * 95)
    print(f"Total Users: {len(rows)}\n")


def test_auth(conn: sqlite3.Connection, username: str, password: str) -> bool:
    """Simulates FastAPI /login authentication logic."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, full_name, university FROM users WHERE username = ? AND password = ?",
        (username, password),
    )
    user = cursor.fetchone()
    if user:
        print(f"  [SUCCESS] Authenticated: {user['full_name']} ({user['username']}) - {user['university']}")
        return True
    else:
        print(f"  [FAILED] Invalid credentials for '{username}'")
        return False


def add_custom_user(conn: sqlite3.Connection, username: str, password: str, full_name: str, university: str) -> bool:
    """Inserts a single new user into the database."""
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute(
            """
            INSERT INTO users (username, password, full_name, university, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, password, full_name, university, now_str)
        )
        conn.commit()
        print(f"[SUCCESS] User '{username}' successfully registered with ID {cursor.lastrowid}.")
        return True
    except sqlite3.IntegrityError:
        print(f"[ERROR] Username '{username}' already exists.")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CardioMate SQLite Database Seeder & Manager")
    parser.add_argument("--list", action="store_true", help="List all users in the database")
    parser.add_argument("--seed", action="store_true", help="Seed default doctor and student users")
    parser.add_argument("--add-user", nargs=4, metavar=("USERNAME", "PASSWORD", "FULL_NAME", "UNIVERSITY"),
                        help="Add a custom user: --add-user username password 'Full Name' 'University'")
    parser.add_argument("--test-login", nargs=2, metavar=("USERNAME", "PASSWORD"),
                        help="Test user authentication against database")

    args = parser.parse_args()
    conn = get_connection()
    init_database(conn)

    if args.list:
        list_users(conn)
    elif args.add_user:
        u, p, name, uni = args.add_user
        add_custom_user(conn, u, p, name, uni)
        list_users(conn)
    elif args.test_login:
        u, p = args.test_login
        test_auth(conn, u, p)
    else:
        # Default behavior: initialize, seed, display, and test
        print(f"Connecting to database: {DB_FILE}")
        print("Initializing database tables...")
        print("Seeding sample user accounts...")
        added = seed_sample_users(conn)
        print(f"Added {added} new users to the database.")

        print("\n--- Current Users in cardiomate_history.db ---")
        list_users(conn)

        print("--- Verifying Authentication (CardioMate Login simulation) ---")
        test_auth(conn, "crushbek2008", "12265105")
        test_auth(conn, "dr_jasur", "cardioPass#2026")
        test_auth(conn, "admin", "AdminCardio2026!")

        print("\nDatabase setup and seeding completed successfully!")

    conn.close()


if __name__ == "__main__":
    main()
