import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "test_results.db")

def db_init():
    con = sqlite3.connect(DB_PATH)
    con.close()

def create_results_table():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            username TEXT,
            score INTEGER,
            total INTEGER,
            answers TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()
    con.close()

def save_test_result(telegram_id, username, score, total, answers):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO test_results (telegram_id, username, score, total, answers)
        VALUES (?, ?, ?, ?, ?)
    """, (telegram_id, username, score, total, ",".join(answers)))
    con.commit()
    con.close()

def get_all_results():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM test_results ORDER BY created_at DESC")
    results = cur.fetchall()
    con.close()
    return [dict(r) for r in results]
