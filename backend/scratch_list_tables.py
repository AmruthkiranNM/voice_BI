import sqlite3
from config import DATABASE_PATH
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [row[0] for row in cursor.fetchall()])
conn.close()
