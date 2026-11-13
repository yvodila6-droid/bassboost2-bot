import sqlite3
import os

DB_NAME = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS favorites
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, file_id TEXT, caption TEXT)''')
    conn.commit()
    conn.close()

def add_to_favorites(user_id, file_id, caption):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO favorites (user_id, file_id, caption) VALUES (?, ?, ?)", (user_id, file_id, caption))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id

def get_favorites(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, caption FROM favorites WHERE user_id = ?", (user_id,))
    results = cursor.fetchall()
    conn.close()
    return results